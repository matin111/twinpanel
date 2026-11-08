from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..deps import require_admin
from ..models import Node, NodeType, Plan, ProtocolCredential, Subscription, SubscriptionNode, SubscriptionProtocol, User
from ..subscription_override_models import SubscriptionRuntimeOverride
from ..plan_template_selection import plan_template_node_ids
from ..protocol_account_registry import ALL_PROTOCOL_KEYS, normalize_protocols, plan_protocols
from ..subscription_enforcement import queue_subscription_enforcement
from .subscription_protocol_lifecycle_v2 import _resolve_traffic_limit_bytes
from .subscription_protocol_lifecycle_v3 import (
    _current_exit_node_ids,
    _unique_node_ids,
    admin_edit_subscription_protocol_lifecycle_v3,
)


router = APIRouter(dependencies=[Depends(require_admin)])


async def _reconcile_snapshot_background(subscription_id: int) -> None:
    db = SessionLocal()
    try:
        from .modern_account_delivery_v1 import provision_account_v1
        from ..services.quota_refresh import sync_subscription_quota_nodes

        try:
            result = await provision_account_v1(subscription_id=subscription_id, db=db)
            if not bool((result or {}).get("ok", False)) or (result or {}).get("errors"):
                print(
                    "TWINPANEL_ADMIN_EDIT_BACKGROUND_DEGRADED_V1",
                    {
                        "subscription_id": int(subscription_id),
                        "errors": list((result or {}).get("errors") or [])[:10],
                    },
                    flush=True,
                )
        except Exception as exc:
            db.rollback()
            print(
                "TWINPANEL_ADMIN_EDIT_BACKGROUND_PROVISION_FAILED_V1",
                {"subscription_id": int(subscription_id), "error": str(exc)[:1200]},
                flush=True,
            )
            return

        try:
            await sync_subscription_quota_nodes(db, int(subscription_id))
        except Exception as exc:
            db.rollback()
            print(
                "TWINPANEL_ADMIN_EDIT_BACKGROUND_QUOTA_DEGRADED_V1",
                {"subscription_id": int(subscription_id), "error": str(exc)[:800]},
                flush=True,
            )
    finally:
        db.close()


async def _legacy_edit_background(subscription_id: int, payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        await admin_edit_subscription_protocol_lifecycle_v3(
            subscription_id=int(subscription_id),
            payload=dict(payload),
            db=db,
        )
    except Exception as exc:
        db.rollback()
        print(
            "TWINPANEL_ADMIN_EDIT_BACKGROUND_LEGACY_FAILED_V1",
            {"subscription_id": int(subscription_id), "error": str(exc)[:1200]},
            flush=True,
        )
    finally:
        db.close()


def _invalid_edit_node_ids(
    desired_node_ids: list[int],
    allowed_node_ids: list[int],
    old_node_ids: list[int],
    *,
    same_plan: bool,
) -> list[int]:
    """Grandfather unchanged existing Exit assignments, never new plan exclusions."""
    allowed = set(allowed_node_ids)
    old = set(old_node_ids) if same_plan else set()
    return [node_id for node_id in desired_node_ids if node_id not in allowed and node_id not in old]


@router.patch("/v1/subscriptions/{subscription_id}/admin-edit", status_code=202)
async def admin_edit_subscription_fast_v1(
    subscription_id: int,
    background_tasks: BackgroundTasks,
    payload: dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    """Persist protocol/server desired-state quickly and provision after response.

    This route deliberately has the same public contract as the historical
    admin-edit endpoint and is mounted before it. Older admin UIs that sent an
    empty node_ids array no longer erase or invalidate the server snapshot: an
    empty list means preserve the subscription's current Exit nodes.
    """

    sub = db.get(Subscription, int(subscription_id))
    if sub is None:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    user = db.get(User, int(sub.user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    # Imported/manual subscriptions intentionally have no commercial Plan.
    # A submitted zero is the explicit "manual, keep no plan" selection.
    requested_plan = payload.get("plan_id", sub.plan_id)
    plan_id = int(requested_plan or 0)
    plan = db.get(Plan, plan_id) if plan_id else None
    if plan is not None and not bool(plan.is_active):
        raise HTTPException(status_code=422, detail="پلن انتخاب‌شده غیرفعال است")
    if plan_id and plan is None:
        raise HTTPException(status_code=404, detail="پلن انتخاب‌شده پیدا نشد")
    if plan is None and sub.plan_id is not None:
        raise HTTPException(status_code=422, detail="اشتراک پلن‌دار را نمی‌توان بدون پلن ذخیره کرد")

    try:
        protocols = normalize_protocols(payload.get("protocols", []))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not protocols:
        raise HTTPException(status_code=422, detail="حداقل یک پروتکل انتخاب کنید")

    allowed_protocols = set(plan_protocols(db, plan)) if plan else set(ALL_PROTOCOL_KEYS)
    not_in_plan = [protocol for protocol in protocols if protocol not in allowed_protocols]
    if not_in_plan:
        raise HTTPException(
            status_code=422,
            detail="این پروتکل‌ها در پلن فعال نیستند: " + ", ".join(not_in_plan),
        )

    old_node_ids = _current_exit_node_ids(db, int(sub.id))
    requested_node_ids = _unique_node_ids(payload.get("node_ids")) if "node_ids" in payload else []
    # Compatibility: several recent UIs accidentally submitted node_ids: [].
    # Preserve the existing snapshot instead of rejecting the edit or clearing it.
    allowed_node_ids = plan_template_node_ids(db, int(plan.id)) if plan else list(old_node_ids)
    # Changing the commercial plan is an intentional switch to the new plan's
    # node snapshot; the old nodes may not be included in the new template.
    if plan is not None and sub.plan_id != int(plan.id):
        desired_node_ids = requested_node_ids or list(allowed_node_ids)
    else:
        desired_node_ids = requested_node_ids or list(old_node_ids)
    if not desired_node_ids:
        desired_node_ids = list(allowed_node_ids)
    if not desired_node_ids:
        raise HTTPException(status_code=422, detail="حداقل یک سرور خروجی انتخاب کنید")

    # An unchanged subscription/plan can retain previously allocated Exit
    # nodes even when a plan template was subsequently narrowed. Do not grant
    # any new out-of-plan node, and enforce the new template on plan changes.
    # Existing nodes are still checked below for Exit type and retirement.
    same_plan = (plan is None and sub.plan_id is None) or (
        plan is not None and sub.plan_id == int(plan.id)
    )
    invalid_nodes = _invalid_edit_node_ids(
        desired_node_ids, allowed_node_ids, old_node_ids, same_plan=same_plan,
    )
    if invalid_nodes:
        raise HTTPException(
            status_code=422,
            detail="این سرورها در پلن مجاز نیستند: " + ", ".join(str(value) for value in invalid_nodes),
        )

    valid_count = (
        db.query(Node)
        .filter(
            Node.id.in_(desired_node_ids),
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
        )
        .count()
    )
    if valid_count != len(set(desired_node_ids)):
        raise HTTPException(status_code=422, detail="یک یا چند سرور خروجی معتبر نیست")

    # Optional per-account limits are never inferred for older API clients.
    new_device_limit = None
    if "device_limit" in payload:
        try:
            new_device_limit = int(payload["device_limit"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="تعداد اتصال هم‌زمان نامعتبر است")
        if not 0 <= new_device_limit <= 1000:
            raise HTTPException(status_code=422, detail="تعداد دستگاه باید بین ۰ و ۱۰۰۰ باشد")

    new_duration_days = None
    if "duration_days" in payload:
        try:
            new_duration_days = int(payload["duration_days"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="مدت اشتراک نامعتبر است")
        if not 0 <= new_duration_days <= 3650:
            raise HTTPException(status_code=422, detail="مدت اشتراک باید بین ۰ و ۳۶۵۰ روز باشد")

    expiry_sent = "expires_at" in payload
    new_expires_at = None
    if expiry_sent and payload["expires_at"] not in (None, ""):
        try:
            parsed = datetime.fromisoformat(str(payload["expires_at"]).replace("Z", "+00:00"))
            new_expires_at = parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except (ValueError, TypeError, OverflowError):
            raise HTTPException(status_code=422, detail="تاریخ انقضا نامعتبر است")
        if new_expires_at <= datetime.utcnow():
            raise HTTPException(status_code=422, detail="تاریخ انقضا باید در آینده باشد")

    requested_username = str(payload.get("account_username") or "").strip()
    username_changed = bool(requested_username and requested_username != str(sub.account_username or ""))
    password_changed = bool(str(payload.get("account_password") or "").strip())

    normalized_payload = dict(payload)
    normalized_payload["node_ids"] = list(desired_node_ids)
    normalized_payload["protocols"] = list(protocols)

    def persist_account_limits():
        if new_device_limit is not None:
            override = db.get(SubscriptionRuntimeOverride, int(sub.id))
            if override is None:
                override = SubscriptionRuntimeOverride(subscription_id=int(sub.id))
                db.add(override)
            override.device_limit = new_device_limit
        if new_duration_days is not None:
            sub.activation_duration_days = new_duration_days
            if sub.starts_at is not None and not expiry_sent and new_duration_days:
                sub.expires_at = sub.starts_at + timedelta(days=new_duration_days)
        if expiry_sent:
            sub.expires_at = new_expires_at
            if new_expires_at and sub.starts_at is None:
                sub.activation_duration_days = max(1, (new_expires_at - datetime.utcnow()).days + 1)


    # Credential rotations need the historical shared-login synchronization.
    # They still run after the HTTP response so the UI never waits on SSH.
    if (username_changed or password_changed) and plan is None:
        raise HTTPException(
            status_code=422,
            detail="برای تغییر نام کاربری یا رمز اشتراک دستی، ابتدا یک پلن انتخاب کنید",
        )
    if username_changed or password_changed:
        persist_account_limits()
        db.commit()
        background_tasks.add_task(
            _legacy_edit_background,
            int(subscription_id),
            normalized_payload,
        )
        return {
            "ok": True,
            "queued": True,
            "subscription_id": int(subscription_id),
            "node_ids": desired_node_ids,
            "protocols": protocols,
            "credential_change": True,
            "message": "تغییرات ثبت شد؛ بروزرسانی اکانت در پس‌زمینه ادامه دارد",
        }

    old_protocols = {
        str(row[0]).strip().lower()
        for row in db.query(SubscriptionProtocol.protocol)
        .filter(SubscriptionProtocol.subscription_id == int(sub.id))
        .all()
    }
    desired_protocol_set = set(protocols)
    old_node_set = set(old_node_ids)
    desired_node_set = set(desired_node_ids)
    removed_protocols = sorted(old_protocols - desired_protocol_set)
    removed_nodes = sorted(old_node_set - desired_node_set)

    try:
        sub.plan_id = int(plan.id) if plan else None
        persist_account_limits()
        sub.traffic_limit_bytes = _resolve_traffic_limit_bytes(sub, payload)
        sub.iran_node_id = None
        sub.exit_node_id = int(desired_node_ids[0])

        if removed_nodes and old_protocols:
            queue_subscription_enforcement(
                db,
                sub,
                command_type="revoke_subscription",
                reason="node_removed_fast_v1",
                protocols=sorted(old_protocols),
                node_ids=removed_nodes,
            )
        if removed_protocols and old_node_ids:
            queue_subscription_enforcement(
                db,
                sub,
                command_type="revoke_subscription",
                reason="protocol_removed_fast_v1",
                protocols=removed_protocols,
                node_ids=old_node_ids,
            )

        db.query(SubscriptionNode).filter(
            SubscriptionNode.subscription_id == int(sub.id)
        ).delete(synchronize_session=False)
        for node_id in desired_node_ids:
            db.add(SubscriptionNode(subscription_id=int(sub.id), node_id=int(node_id)))

        db.query(SubscriptionProtocol).filter(
            SubscriptionProtocol.subscription_id == int(sub.id)
        ).delete(synchronize_session=False)
        for protocol in protocols:
            db.add(SubscriptionProtocol(subscription_id=int(sub.id), protocol=protocol))

        if removed_protocols:
            db.query(ProtocolCredential).filter(
                ProtocolCredential.subscription_id == int(sub.id),
                ProtocolCredential.protocol.in_(removed_protocols),
            ).update({ProtocolCredential.is_active: False}, synchronize_session=False)

        db.commit()
    except Exception:
        db.rollback()
        raise

    background_tasks.add_task(_reconcile_snapshot_background, int(subscription_id))
    return {
        "ok": True,
        "queued": True,
        "subscription_id": int(subscription_id),
        "node_ids": desired_node_ids,
        "protocols": protocols,
        "credential_change": False,
        "message": "پروتکل‌ها و سرورها ذخیره شدند؛ ساخت کانفیگ‌ها در پس‌زمینه ادامه دارد",
    }
