from __future__ import annotations

import re
import shlex
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import (
    Node,
    NodeProtocolConfig,
    NodeType,
    Plan,
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    User,
)
from ..protocol_account_registry import (
    CLASSIC_PLAN_FIELDS,
    MODERN_PROTOCOL_KEYS,
    normalize_protocols,
    plan_protocols,
)
from ..subscription_enforcement import queue_subscription_enforcement


router = APIRouter(dependencies=[Depends(require_admin)])
MODERN_PROTOCOL_SET = frozenset(MODERN_PROTOCOL_KEYS)


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _is_exit(node: Node) -> bool:
    return _status_value(node.node_type) == _status_value(NodeType.EXIT)


def _credential(
    db: Session,
    subscription_id: int,
    protocol: str,
) -> ProtocolCredential | None:
    return (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == int(subscription_id),
            ProtocolCredential.protocol == str(protocol),
        )
        .first()
    )


def _reusable_credential(protocol: str, cred: ProtocolCredential | None) -> bool:
    if cred is None or not cred.config_text_encrypted:
        return False
    if protocol in MODERN_PROTOCOL_SET:
        return bool(cred.secret_encrypted)
    return True


def _modern_runtime_online(
    db: Session,
    node_ids: list[int],
    protocol: str,
) -> bool:
    if not node_ids:
        return False
    rows = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id.in_(node_ids),
            NodeProtocolConfig.protocol == protocol,
        )
        .all()
    )
    return any(_status_value(row.status) == "online" for row in rows)


async def _sync_shared_login(
    *,
    ad: Any,
    db: Session,
    sub: Subscription,
    user: User,
    nodes: list[Node],
    protocol: str,
    username: str,
    password: str,
    old_username: str,
    username_changed: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Update Cisco/L2TP login without touching unrelated protocol identities."""

    flag = CLASSIC_PLAN_FIELDS[protocol]
    items: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for node in nodes:
        if not bool(getattr(node, flag, False)):
            continue
        try:
            if protocol == "cisco":
                item = await ad._cisco(db, node, sub, user, username, password)
            else:
                item = await ad._l2tp(db, node, sub, user, username, password)
            items.append(item)
        except Exception as exc:
            errors.append(
                {
                    "protocol": protocol,
                    "node_id": int(node.id),
                    "node": str(node.name),
                    "error": f"credential update failed: {str(exc)[:700]}",
                }
            )
            continue

        if not username_changed or not old_username or old_username == username:
            continue

        cleanup_conn = None
        try:
            cleanup_conn = await ad.ssh_connect_saved(node, db)
            if protocol == "cisco":
                await ad.cmd(
                    cleanup_conn,
                    "ocpasswd -c /etc/ocserv/ocpasswd -d "
                    + shlex.quote(old_username)
                    + " || true",
                )
            else:
                escaped = re.escape(old_username)
                await ad.cmd(
                    cleanup_conn,
                    "grep -v '^"
                    + escaped
                    + "[[:space:]]' /etc/ppp/chap-secrets "
                    "> /tmp/tpchap-edit.$$ || true; "
                    "cat /tmp/tpchap-edit.$$ > /etc/ppp/chap-secrets; "
                    "rm -f /tmp/tpchap-edit.$$; chmod 600 /etc/ppp/chap-secrets",
                )
        except Exception as exc:
            errors.append(
                {
                    "protocol": protocol,
                    "node_id": int(node.id),
                    "node": str(node.name),
                    "error": f"old username cleanup failed: {str(exc)[:700]}",
                }
            )
        finally:
            if cleanup_conn is not None:
                cleanup_conn.close()
                try:
                    await cleanup_conn.wait_closed()
                except Exception:
                    pass

    return items, errors


@router.patch("/v1/subscriptions/{subscription_id}/admin-edit")
async def admin_edit_subscription_protocol_lifecycle_v2(
    subscription_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """Canonical SubscriptionProtocol lifecycle for all 15 protocols.

    PlanProtocol is only the plan-level allowance/default. SubscriptionProtocol
    remains the final desired state. Re-enabling a previously provisioned
    protocol reuses its stored ProtocolCredential and queues a restore instead
    of rotating keys, UUIDs, usernames, or passwords.
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

    plan_id = int(payload.get("plan_id") or sub.plan_id)
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="پلن پیدا نشد")

    traffic_gb = float(payload.get("traffic_gb", 0) or 0)
    if traffic_gb <= 0:
        raise HTTPException(status_code=422, detail="حجم نامعتبر است")

    new_limit = int(traffic_gb * 1024**3)
    if new_limit < int(sub.traffic_used_bytes or 0):
        raise HTTPException(status_code=422, detail="حجم کل کمتر از مصرف فعلی است")

    try:
        protocols = normalize_protocols(payload.get("protocols", []))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not protocols:
        raise HTTPException(status_code=422, detail="حداقل یک پروتکل انتخاب کنید")

    allowed = set(plan_protocols(db, plan))
    not_in_plan = [protocol for protocol in protocols if protocol not in allowed]
    if not_in_plan:
        raise HTTPException(
            status_code=422,
            detail="این پروتکل‌ها در پلن فعال نیستند: " + ", ".join(not_in_plan),
        )

    nodes = (
        db.query(Node)
        .filter(Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )
    exit_nodes = [node for node in nodes if _is_exit(node)]
    exit_ids = [int(node.id) for node in exit_nodes]

    if not exit_nodes:
        raise HTTPException(status_code=409, detail="هیچ سرور خروجی معتبری وجود ندارد")

    unsupported: list[str] = []
    for protocol in protocols:
        if protocol in CLASSIC_PLAN_FIELDS:
            flag = CLASSIC_PLAN_FIELDS[protocol]
            if not any(bool(getattr(node, flag, False)) for node in exit_nodes):
                unsupported.append(protocol)
        elif protocol in MODERN_PROTOCOL_SET:
            if not _modern_runtime_online(db, exit_ids, protocol):
                unsupported.append(protocol)
        else:
            unsupported.append(protocol)

    if unsupported:
        raise HTTPException(
            status_code=422,
            detail="سرورهای خروجی Runtime آماده برای این پروتکل‌ها ندارند: "
            + ", ".join(unsupported),
        )

    old_protocols = {
        str(row.protocol).strip().lower()
        for row in (
            db.query(SubscriptionProtocol)
            .filter(SubscriptionProtocol.subscription_id == sub.id)
            .all()
        )
    }
    desired_protocols = set(protocols)
    added_protocols = desired_protocols - old_protocols
    removed_protocols = old_protocols - desired_protocols

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
    restored_protocols: list[str] = []
    restore_candidates: list[str] = []
    revoke_result: dict[str, Any] = {"commands": [], "commands_created": 0}
    restore_result: dict[str, Any] = {"commands": [], "commands_created": 0}

    try:
        sub.plan_id = plan.id
        sub.traffic_limit_bytes = new_limit
        sub.account_username = username
        sub.account_password_encrypted = password

        # Global infrastructure membership: every non-retired node belongs to
        # the subscription. Do this before enforcement so global revoke/restore
        # reaches every current Exit and updates quota devices globally.
        (
            db.query(SubscriptionNode)
            .filter(SubscriptionNode.subscription_id == sub.id)
            .delete(synchronize_session=False)
        )
        for node in nodes:
            db.add(SubscriptionNode(subscription_id=sub.id, node_id=int(node.id)))
        db.flush()

        # OFF must revoke the still-active identity before its credential is
        # marked inactive or the selected-protocol row is removed.
        if removed_protocols:
            revoke_result = queue_subscription_enforcement(
                db,
                sub,
                command_type="revoke_subscription",
                reason="protocol_removed_v2",
                protocols=sorted(removed_protocols),
                node_ids=None,
            )

        (
            db.query(SubscriptionProtocol)
            .filter(SubscriptionProtocol.subscription_id == sub.id)
            .delete(synchronize_session=False)
        )
        for protocol in protocols:
            db.add(SubscriptionProtocol(subscription_id=sub.id, protocol=protocol))
        db.flush()

        if removed_protocols:
            (
                db.query(ProtocolCredential)
                .filter(
                    ProtocolCredential.subscription_id == sub.id,
                    ProtocolCredential.protocol.in_(sorted(removed_protocols)),
                )
                .update(
                    {ProtocolCredential.is_active: False},
                    synchronize_session=False,
                )
            )

        for protocol in protocols:
            cred = _credential(db, sub.id, protocol)
            reusable = _reusable_credential(protocol, cred)

            if reusable:
                if not bool(cred.is_active):
                    cred.is_active = True
                reused_pairs.append(
                    {
                        "protocol": protocol,
                        "credential_reused": True,
                    }
                )
                if protocol in added_protocols:
                    restore_candidates.append(protocol)
                continue

            if protocol in MODERN_PROTOCOL_SET:
                items, errors = await _provision_modern_protocol(
                    ad,
                    db,
                    sub,
                    protocol,
                    exit_nodes,
                )
            else:
                items, errors = await _provision_classic_protocol(
                    ad,
                    db,
                    sub,
                    user,
                    protocol,
                    exit_nodes,
                    username,
                    password,
                    str(uuid.uuid4()),
                )

            provision_errors.extend(errors)
            for item in items:
                created_pairs.append(
                    {
                        "protocol": protocol,
                        "node_id": int(item.get("node_id") or 0),
                    }
                )

        # Re-enable uses the exact stored identity. The enforcement layer has a
        # controller-owned executor for Modern protocols and the existing Agent
        # executor for Classic protocols.
        reusable_added = sorted(set(restore_candidates))
        if reusable_added:
            restore_result = queue_subscription_enforcement(
                db,
                sub,
                command_type="restore_subscription",
                reason="protocol_reenabled_v2",
                protocols=reusable_added,
                node_ids=None,
            )
            restored_protocols = reusable_added

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
            {
                "protocol": "quota",
                "node": "quota-agent",
                "error": str(exc)[:800],
            }
        )

    return {
        "ok": len(provision_errors) == 0 and bool(quota_sync.get("ok", True)),
        "subscription_id": sub.id,
        "added_protocols": sorted(added_protocols),
        "removed_protocols": sorted(removed_protocols),
        "created_pairs": created_pairs,
        "reused_pairs": reused_pairs,
        "restored_protocols": sorted(set(restored_protocols)),
        "provision_errors": provision_errors,
        "revoke": revoke_result,
        "restore": restore_result,
        "quota": quota_sync,
    }
