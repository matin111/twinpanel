from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import (
    Node,
    NodeType,
    Plan,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    User,
)
from ..plan_template_selection import plan_template_node_ids
from ..protocol_account_registry import (
    CLASSIC_PLAN_FIELDS,
    normalize_protocols,
    plan_protocols,
)
from ..subscription_enforcement import queue_subscription_enforcement
from .subscription_protocol_lifecycle_v2 import (
    MODERN_PROTOCOL_SET,
    _credential,
    _modern_runtime_online,
    _resolve_traffic_limit_bytes,
    _reusable_credential,
    _sync_shared_login,
)


router = APIRouter(dependencies=[Depends(require_admin)])


def _unique_node_ids(values: Any) -> list[int]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise HTTPException(status_code=422, detail="node_ids must be a list")
    result: list[int] = []
    for raw in values:
        try:
            node_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="شناسه سرور معتبر نیست") from exc
        if node_id <= 0:
            raise HTTPException(status_code=422, detail="شناسه سرور معتبر نیست")
        if node_id not in result:
            result.append(node_id)
    return result


def _current_exit_node_ids(db: Session, subscription_id: int) -> list[int]:
    return [
        int(row[0])
        for row in (
            db.query(SubscriptionNode.node_id)
            .join(Node, Node.id == SubscriptionNode.node_id)
            .filter(
                SubscriptionNode.subscription_id == int(subscription_id),
                Node.node_type == NodeType.EXIT,
                Node.retired_at.is_(None),
            )
            .order_by(SubscriptionNode.id.asc())
            .all()
        )
    ]


def _credential_items(ad: Any, cred: ProtocolCredential | None) -> list[dict[str, Any]]:
    if cred is None or not cred.config_text_encrypted:
        return []
    decoded = ad._dec(cred.config_text_encrypted)
    if isinstance(decoded, dict):
        decoded = [decoded]
    if not isinstance(decoded, list):
        return []
    return [dict(item) for item in decoded if isinstance(item, dict)]


def _filter_credential_items(
    ad: Any,
    cred: ProtocolCredential | None,
    desired_node_ids: list[int],
) -> list[dict[str, Any]]:
    if cred is None:
        return []
    allowed = set(desired_node_ids)
    items = [
        item
        for item in _credential_items(ad, cred)
        if int(item.get("node_id") or 0) in allowed
    ]
    if items:
        cred.config_text_encrypted = ad._enc(items)
    return items


def _merge_credential_items(
    ad: Any,
    cred: ProtocolCredential,
    previous: list[dict[str, Any]],
    created: list[dict[str, Any]],
    desired_node_ids: list[int],
) -> list[dict[str, Any]]:
    by_node: dict[int, dict[str, Any]] = {}
    for item in previous + created:
        try:
            node_id = int(item.get("node_id") or 0)
        except (TypeError, ValueError):
            continue
        if node_id > 0:
            by_node[node_id] = item
    merged = [by_node[node_id] for node_id in desired_node_ids if node_id in by_node]
    if merged:
        cred.config_text_encrypted = ad._enc(merged)
    return merged


@router.patch("/v1/subscriptions/{subscription_id}/admin-edit")
async def admin_edit_subscription_protocol_lifecycle_v3(
    subscription_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Snapshot-aware admin edit for protocol and server desired-state.

    Node selection is immutable subscription desired-state. Iran nodes are
    tunnel infrastructure and never become SubscriptionNode targets. The Mother
    is available only when the central mother policy allows it. Tunnel presence
    is intentionally not an eligibility requirement: a healthy Exit may deliver
    directly when it has no active Iran tunnel.
    """

    from . import account_delivery as ad
    from .modern_account_delivery_v1 import (
        _provision_classic_protocol,
        _provision_modern_protocol,
    )

    sub = db.get(Subscription, int(subscription_id))
    if sub is None:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    user = db.get(User, sub.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="کاربر پیدا نشد")

    plan_id = int(payload.get("plan_id") or sub.plan_id or 0)
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")

    new_limit = _resolve_traffic_limit_bytes(sub, payload)
    try:
        protocols = normalize_protocols(payload.get("protocols", []))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not protocols:
        raise HTTPException(status_code=422, detail="حداقل یک پروتکل انتخاب کنید")

    allowed_protocols = set(plan_protocols(db, plan))
    not_in_plan = [protocol for protocol in protocols if protocol not in allowed_protocols]
    if not_in_plan:
        raise HTTPException(
            status_code=422,
            detail="این پروتکل‌ها در پلن فعال نیستند: " + ", ".join(not_in_plan),
        )

    allowed_node_ids = plan_template_node_ids(db, int(plan.id))
    old_target_node_ids = _current_exit_node_ids(db, sub.id)
    if "node_ids" in payload:
        desired_node_ids = _unique_node_ids(payload.get("node_ids"))
        if not desired_node_ids:
            raise HTTPException(status_code=422, detail="حداقل یک سرور خروجی انتخاب کنید")
    else:
        desired_node_ids = [node_id for node_id in old_target_node_ids if node_id in allowed_node_ids]
        if not desired_node_ids:
            desired_node_ids = list(allowed_node_ids)

    invalid_nodes = [node_id for node_id in desired_node_ids if node_id not in allowed_node_ids]
    if invalid_nodes:
        raise HTTPException(
            status_code=422,
            detail=(
                "این سرورها در پلن مجاز نیستند، Exit معتبر نیستند یا سرور مادر غیرفعال است: "
                + ", ".join(str(node_id) for node_id in invalid_nodes)
            ),
        )

    node_rows = (
        db.query(Node)
        .filter(
            Node.id.in_(desired_node_ids),
            Node.node_type == NodeType.EXIT,
            Node.retired_at.is_(None),
        )
        .all()
    )
    nodes_by_id = {int(node.id): node for node in node_rows}
    exit_nodes = [nodes_by_id[node_id] for node_id in desired_node_ids if node_id in nodes_by_id]
    if len(exit_nodes) != len(desired_node_ids):
        raise HTTPException(status_code=422, detail="یک یا چند سرور خروجی معتبر نیست")

    unsupported: list[str] = []
    for protocol in protocols:
        if protocol in CLASSIC_PLAN_FIELDS:
            flag = CLASSIC_PLAN_FIELDS[protocol]
            if not any(bool(getattr(node, flag, False)) for node in exit_nodes):
                unsupported.append(protocol)
        elif protocol in MODERN_PROTOCOL_SET:
            if not _modern_runtime_online(db, desired_node_ids, protocol):
                unsupported.append(protocol)
        else:
            unsupported.append(protocol)
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail="سرورهای انتخاب‌شده Runtime آماده برای این پروتکل‌ها ندارند: "
            + ", ".join(unsupported),
        )

    old_protocols = {
        str(row.protocol).strip().lower()
        for row in db.query(SubscriptionProtocol)
        .filter(SubscriptionProtocol.subscription_id == sub.id)
        .all()
    }
    desired_protocols = set(protocols)
    added_protocols = desired_protocols - old_protocols
    removed_protocols = old_protocols - desired_protocols
    old_node_set = set(old_target_node_ids)
    desired_node_set = set(desired_node_ids)
    added_node_ids = sorted(desired_node_set - old_node_set)
    removed_node_ids = sorted(old_node_set - desired_node_set)

    old_username = str(sub.account_username or ad._safe_username(sub, user) or "").strip()
    old_password = str(sub.account_password_encrypted or "")
    username = old_username or ad._safe_username(sub, user)
    password = old_password or ad._numeric_secret(8)

    if "account_username" in payload:
        username = str(payload.get("account_username") or "").strip()
        if not username:
            raise HTTPException(status_code=422, detail="نام کاربری نمی‌تواند خالی باشد")
        if len(username) > 120 or not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
            raise HTTPException(
                status_code=422,
                detail="نام کاربری فقط می‌تواند شامل حروف انگلیسی، عدد، نقطه، خط تیره و زیرخط باشد",
            )
    if "account_password" in payload:
        password = str(payload.get("account_password") or "").strip()
        if not password:
            raise HTTPException(status_code=422, detail="رمز عبور نمی‌تواند خالی باشد")
        if len(password) < 4 or len(password) > 128 or any(ch.isspace() for ch in password):
            raise HTTPException(
                status_code=422,
                detail="رمز عبور باید بین ۴ تا ۱۲۸ کاراکتر و بدون فاصله باشد",
            )

    username_changed = username != old_username
    password_changed = password != old_password
    shared_login_changed = username_changed or password_changed

    provision_errors: list[dict[str, Any]] = []
    created_pairs: list[dict[str, Any]] = []
    reused_pairs: list[dict[str, Any]] = []
    revoke_commands = 0
    restore_commands = 0

    try:
        sub.plan_id = plan.id
        sub.traffic_limit_bytes = new_limit
        sub.account_username = username
        sub.account_password_encrypted = password
        sub.iran_node_id = None
        sub.exit_node_id = int(desired_node_ids[0]) if desired_node_ids else None

        if removed_node_ids and old_protocols:
            result = queue_subscription_enforcement(
                db,
                sub,
                command_type="revoke_subscription",
                reason="node_removed_v3",
                protocols=sorted(old_protocols),
                node_ids=removed_node_ids,
            )
            revoke_commands += int(result.get("commands_created") or 0)

        if removed_protocols and old_target_node_ids:
            result = queue_subscription_enforcement(
                db,
                sub,
                command_type="revoke_subscription",
                reason="protocol_removed_v3",
                protocols=sorted(removed_protocols),
                node_ids=old_target_node_ids,
            )
            revoke_commands += int(result.get("commands_created") or 0)

        db.query(SubscriptionNode).filter(
            SubscriptionNode.subscription_id == sub.id
        ).delete(synchronize_session=False)
        for node_id in desired_node_ids:
            db.add(SubscriptionNode(subscription_id=sub.id, node_id=node_id))

        db.query(SubscriptionProtocol).filter(
            SubscriptionProtocol.subscription_id == sub.id
        ).delete(synchronize_session=False)
        for protocol in protocols:
            db.add(SubscriptionProtocol(subscription_id=sub.id, protocol=protocol))
        db.flush()

        if removed_protocols:
            db.query(ProtocolCredential).filter(
                ProtocolCredential.subscription_id == sub.id,
                ProtocolCredential.protocol.in_(sorted(removed_protocols)),
            ).update({ProtocolCredential.is_active: False}, synchronize_session=False)

        for protocol in protocols:
            cred = _credential(db, sub.id, protocol)
            reusable = _reusable_credential(protocol, cred)
            previous_items = _filter_credential_items(ad, cred, desired_node_ids) if reusable else []
            previous_node_ids = {
                int(item.get("node_id") or 0)
                for item in previous_items
                if int(item.get("node_id") or 0) > 0
            }
            missing_nodes = [
                node for node in exit_nodes
                if int(node.id) not in previous_node_ids
            ]

            if reusable and not missing_nodes:
                if not bool(cred.is_active):
                    cred.is_active = True
                reused_pairs.append({"protocol": protocol, "credential_reused": True})
                if protocol in added_protocols or added_node_ids:
                    result = queue_subscription_enforcement(
                        db,
                        sub,
                        command_type="restore_subscription",
                        reason="desired_state_restored_v3",
                        protocols=[protocol],
                        node_ids=desired_node_ids,
                    )
                    restore_commands += int(result.get("commands_created") or 0)
                continue

            provision_nodes = missing_nodes if reusable and protocol != "v2ray" else exit_nodes
            if protocol in MODERN_PROTOCOL_SET:
                items, errors = await _provision_modern_protocol(
                    ad, db, sub, protocol, provision_nodes
                )
            else:
                items, errors = await _provision_classic_protocol(
                    ad,
                    db,
                    sub,
                    user,
                    protocol,
                    provision_nodes,
                    username,
                    password,
                    str(uuid.uuid4()),
                )
            provision_errors.extend(errors)
            for item in items:
                created_pairs.append(
                    {"protocol": protocol, "node_id": int(item.get("node_id") or 0)}
                )

            cred = _credential(db, sub.id, protocol)
            if cred is not None and previous_items and provision_nodes is not exit_nodes:
                _merge_credential_items(ad, cred, previous_items, items, desired_node_ids)

        if shared_login_changed:
            for protocol in ("cisco", "l2tp"):
                if protocol not in desired_protocols or protocol in added_protocols:
                    continue
                items, errors = await _sync_shared_login(
                    ad=ad,
                    db=db,
                    sub=sub,
                    user=user,
                    nodes=exit_nodes,
                    protocol=protocol,
                    username=username,
                    password=password,
                    old_username=old_username,
                    username_changed=username_changed,
                )
                provision_errors.extend(errors)
                if items:
                    cred = _credential(db, sub.id, protocol)
                    if cred is None:
                        cred = ProtocolCredential(subscription_id=sub.id, protocol=protocol)
                        db.add(cred)
                        db.flush()
                    cred.username = username
                    cred.secret_encrypted = ad._enc({"password": password})
                    cred.config_text_encrypted = ad._enc(items)
                    cred.is_active = True

        db.commit()
        db.refresh(sub)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    quota_sync: dict[str, Any] = {"ok": True, "nodes": []}
    try:
        from ..services.quota_refresh import sync_subscription_quota_nodes

        quota_sync = await sync_subscription_quota_nodes(db, sub.id)
    except Exception as exc:
        quota_sync = {"ok": False, "error": str(exc)[:800], "nodes": []}
        provision_errors.append(
            {"protocol": "quota", "node": "quota-agent", "error": str(exc)[:800]}
        )

    return {
        "ok": len(provision_errors) == 0 and bool(quota_sync.get("ok", True)),
        "subscription_id": int(sub.id),
        "node_ids": desired_node_ids,
        "added_node_ids": added_node_ids,
        "removed_node_ids": removed_node_ids,
        "added_protocols": sorted(added_protocols),
        "removed_protocols": sorted(removed_protocols),
        "created_pairs": created_pairs,
        "reused_pairs": reused_pairs,
        "provision_errors": provision_errors,
        "revoke_commands_created": revoke_commands,
        "restore_commands_created": restore_commands,
        "quota": quota_sync,
    }
