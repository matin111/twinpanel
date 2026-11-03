from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import text

from ..database import SessionLocal, engine
from ..models import NodeType, ProtocolCredential, Subscription, SubscriptionStatus
from . import modern_legacy_reconcile_v1 as legacy


# TWINPANEL_MODERN_RECONCILE_LOCKFIX_V2
#
# Never hold a Subscription row lock while doing SSH/network provisioning.
# PostgreSQL's global lock_timeout is intentionally short (3s), so a
# SELECT ... FOR UPDATE around a slow modern-protocol install caused unrelated
# payment/quota/convergence transactions to fail and left new Exit nodes absent
# from Modern credentials.  A session advisory lock serializes only Modern
# reconciliation for the same subscription without blocking ordinary row
# updates.  The dedicated connection owns the advisory lock until provisioning
# finishes and is always released in finally.
_LOCK_NAMESPACE = 0x54504D52  # "TPMR"
_LOCK_MASK = (1 << 31) - 1


def _lock_key(subscription_id: int) -> int:
    return (int(_LOCK_NAMESPACE) << 31) | (int(subscription_id) & _LOCK_MASK)


@contextmanager
def _subscription_reconcile_guard(subscription_id: int) -> Iterator[bool]:
    if engine.dialect.name != "postgresql":
        yield True
        return

    conn = engine.connect()
    acquired = False
    key = _lock_key(subscription_id)
    try:
        acquired = bool(
            conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": key},
            ).scalar()
        )
        yield acquired
    finally:
        if acquired:
            try:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": key},
                )
            except Exception:
                pass
        conn.close()


async def _reconcile_subscription_modern_accounts_lockfix(
    subscription_id: int,
    *,
    max_protocols: int | None = None,
) -> dict[str, Any]:
    snapshot = legacy._subscription_snapshot(subscription_id)
    if snapshot is None:
        return {
            "ok": False,
            "subscription_id": int(subscription_id),
            "error": "subscription_not_found",
            "repaired": [],
            "ready": [],
            "partial": [],
            "errors": [],
        }

    selected = list(snapshot["selected"])
    states = dict(snapshot["states"])
    ready = [p for p in selected if states.get(p) == "complete"]
    partial = [p for p in selected if states.get(p) == "partial"]
    candidates = [
        p for p in selected if states.get(p) in legacy._LEGACY_REPAIR_STATES
    ]
    if max_protocols is not None:
        candidates = candidates[: max(0, int(max_protocols))]

    result: dict[str, Any] = {
        "ok": True,
        "subscription_id": int(subscription_id),
        "status": snapshot["status"],
        "selected": selected,
        "repaired": [],
        "ready": ready,
        "partial": partial,
        "errors": [],
        "quota": {"ok": True, "nodes": []},
    }

    if snapshot["status"] != SubscriptionStatus.ACTIVE.value:
        result["ok"] = False
        result["error"] = "subscription_not_active"
        return result

    if partial:
        result["ok"] = False
        result["errors"].append(
            {
                "protocol": ",".join(partial),
                "error": "partial_credential_requires_manual_review",
            }
        )

    with _subscription_reconcile_guard(subscription_id) as acquired:
        if not acquired:
            result["ok"] = False
            result["busy"] = True
            result["error"] = "modern_reconcile_busy_retry"
            return result

        for protocol in candidates:
            db = SessionLocal()
            try:
                # Deliberately use a normal read.  The advisory lock above is
                # the cross-process Modern-reconcile guard; the Subscription row
                # remains available to payments, quota and other controllers.
                sub = db.get(Subscription, int(subscription_id))
                if sub is None:
                    db.rollback()
                    result["ok"] = False
                    result["errors"].append(
                        {"protocol": protocol, "error": "subscription_not_found"}
                    )
                    break
                if sub.status != SubscriptionStatus.ACTIVE:
                    db.rollback()
                    result["ok"] = False
                    result["errors"].append(
                        {"protocol": protocol, "error": "subscription_not_active"}
                    )
                    break
                if protocol not in legacy._selected_modern_protocols(db, sub.id):
                    db.rollback()
                    continue

                current = (
                    db.query(ProtocolCredential)
                    .filter(
                        ProtocolCredential.subscription_id == sub.id,
                        ProtocolCredential.protocol == protocol,
                    )
                    .first()
                )
                current_state = legacy._reconcile_credential_state(current)
                if current_state == "complete":
                    db.rollback()
                    if protocol not in result["ready"]:
                        result["ready"].append(protocol)
                    continue
                if current_state == "partial":
                    db.rollback()
                    result["ok"] = False
                    if protocol not in result["partial"]:
                        result["partial"].append(protocol)
                    result["errors"].append(
                        {
                            "protocol": protocol,
                            "error": "partial_credential_requires_manual_review",
                        }
                    )
                    continue

                from . import account_delivery as ad
                from .modern_account_delivery_v1 import _provision_modern_protocol

                nodes = [
                    node
                    for node in ad._nodes(db, sub)
                    if node.node_type == NodeType.EXIT
                    and getattr(node, "retired_at", None) is None
                ]
                if not nodes:
                    db.rollback()
                    result["ok"] = False
                    result["errors"].append(
                        {"protocol": protocol, "error": "no_exit_nodes"}
                    )
                    continue

                items, protocol_errors = await _provision_modern_protocol(
                    ad, db, sub, protocol, nodes
                )
                if protocol_errors:
                    result["ok"] = False
                    result["errors"].extend(dict(item) for item in protocol_errors)
                if not items:
                    db.rollback()
                    result["ok"] = False
                    if not protocol_errors:
                        result["errors"].append(
                            {"protocol": protocol, "error": "runtime_not_ready"}
                        )
                    continue

                credential = (
                    db.query(ProtocolCredential)
                    .filter(
                        ProtocolCredential.subscription_id == sub.id,
                        ProtocolCredential.protocol == protocol,
                    )
                    .first()
                )
                if legacy.credential_state(credential) != "complete":
                    db.rollback()
                    result["ok"] = False
                    result["errors"].append(
                        {"protocol": protocol, "error": "credential_not_complete"}
                    )
                    continue

                credential_id = int(credential.id)
                node_ids = [
                    int(item.get("node_id") or 0)
                    for item in items
                    if isinstance(item, dict) and int(item.get("node_id") or 0) > 0
                ]
                db.commit()
                result["repaired"].append(
                    {
                        "protocol": protocol,
                        "credential_id": credential_id,
                        "node_ids": node_ids,
                    }
                )
            except asyncio.CancelledError:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                result["ok"] = False
                result["errors"].append(
                    {
                        "protocol": protocol,
                        "error": f"{type(exc).__name__}:{str(exc)[:700]}",
                    }
                )
            finally:
                db.close()

    if result["repaired"]:
        from ..services.quota_refresh import sync_subscription_quota_nodes

        quota_db = SessionLocal()
        try:
            result["quota"] = await sync_subscription_quota_nodes(
                quota_db, int(subscription_id)
            )
            if not result["quota"].get("ok"):
                result["ok"] = False
                result["errors"].append(
                    {"protocol": "quota", "error": "quota_sync_failed"}
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result["ok"] = False
            result["quota"] = {"ok": False, "nodes": []}
            result["errors"].append(
                {
                    "protocol": "quota",
                    "error": f"{type(exc).__name__}:{str(exc)[:700]}",
                }
            )
        finally:
            quota_db.close()

    return result


# Both the admin route and the background scanner resolve this module global at
# call time, so one compatibility patch fixes every legacy Modern repair path.
legacy._reconcile_subscription_modern_accounts = (
    _reconcile_subscription_modern_accounts_lockfix
)

print(
    "TWINPANEL_MODERN_RECONCILE_LOCKFIX_V2_ACTIVE "
    "guard=pg_advisory_lock subscription_row_lock=disabled network_under_row_lock=0",
    flush=True,
)
