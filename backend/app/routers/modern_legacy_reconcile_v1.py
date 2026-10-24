from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..deps import require_admin
from ..models import (
    NodeType,
    ProtocolCredential,
    Subscription,
    SubscriptionProtocol,
    SubscriptionStatus,
)
from ..protocol_account_registry import MODERN_PROTOCOL_KEYS


logger = logging.getLogger(__name__)

_BACKGROUND_INITIAL_DELAY_SECONDS = 15.0
_BACKGROUND_IDLE_SECONDS = 30.0
_BACKGROUND_BUSY_SECONDS = 5.0
_BACKGROUND_SCAN_LIMIT = 100
_BACKGROUND_MAX_PROTOCOLS = 2
_LEGACY_REPAIR_STATES = frozenset(
    {
        "missing",
        "legacy_empty",
        "legacy_naive_client",
        "legacy_amneziawg_egress",
    }
)

_reconcile_lock = asyncio.Lock()
_scan_cursor = 0


def credential_state(credential: ProtocolCredential | None) -> str:
    """Classify only the storage state; never infer a credential identity."""

    if credential is None:
        return "missing"

    has_secret = bool(str(credential.secret_encrypted or "").strip())
    has_config = bool(str(credential.config_text_encrypted or "").strip())

    if has_secret and has_config:
        return "complete"
    if not has_secret and not has_config:
        return "legacy_empty"
    return "partial"


def _reconcile_credential_state(credential: ProtocolCredential | None) -> str:
    """Extend storage state with safe, identity-preserving legacy repairs."""

    state = credential_state(credential)
    if state != "complete" or credential is None:
        return state

    protocol = str(credential.protocol or "").strip().lower()
    if protocol not in {"naive", "amneziawg"}:
        return state

    try:
        from . import account_delivery as ad

        payload = ad._dec(credential.config_text_encrypted)
    except Exception:
        # Never rotate or rewrite a complete credential merely because an
        # inspection path failed. Normal delivery/error handling remains the
        # authority when encrypted material cannot be decoded safely.
        return state

    if isinstance(payload, list):
        items = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        nested = payload.get("items")
        if isinstance(nested, list):
            items = [item for item in nested if isinstance(item, dict)]
        else:
            items = [payload] if payload else []
    else:
        items = []

    if protocol == "naive":
        try:
            from ..singbox_subscription_accounts import naive_client_item_requires_repair
        except Exception:
            return state
        if any(naive_client_item_requires_repair(item) for item in items):
            return "legacy_naive_client"

    if protocol == "amneziawg" and items:
        try:
            from ..amneziawg_egress_v221 import EGRESS_CONTRACT
        except Exception:
            return state
        if any(int(item.get("egress_contract") or 0) < EGRESS_CONTRACT for item in items):
            return "legacy_amneziawg_egress"

    return state


def _selected_modern_protocols(db: Session, subscription_id: int) -> list[str]:
    selected = {
        str(row[0]).strip().lower()
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == int(subscription_id))
            .all()
        )
    }
    return [protocol for protocol in MODERN_PROTOCOL_KEYS if protocol in selected]


def _credential_map(
    db: Session,
    subscription_id: int,
    protocols: list[str],
) -> dict[str, ProtocolCredential]:
    if not protocols:
        return {}
    rows = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == int(subscription_id),
            ProtocolCredential.protocol.in_(protocols),
        )
        .all()
    )
    return {str(row.protocol).strip().lower(): row for row in rows}


def _subscription_snapshot(subscription_id: int) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        sub = db.get(Subscription, int(subscription_id))
        if sub is None:
            return None

        selected = _selected_modern_protocols(db, sub.id)
        credentials = _credential_map(db, sub.id, selected)
        states = {
            protocol: _reconcile_credential_state(credentials.get(protocol))
            for protocol in selected
        }
        return {
            "subscription_id": int(sub.id),
            "status": str(getattr(sub.status, "value", sub.status) or "").strip().lower(),
            "selected": selected,
            "states": states,
        }
    finally:
        db.close()


async def _reconcile_subscription_modern_accounts(
    subscription_id: int,
    *,
    max_protocols: int | None = None,
) -> dict[str, Any]:
    snapshot = _subscription_snapshot(subscription_id)
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
    ready = [
        protocol
        for protocol in selected
        if states.get(protocol) == "complete"
    ]
    partial = [
        protocol
        for protocol in selected
        if states.get(protocol) == "partial"
    ]
    candidates = [
        protocol
        for protocol in selected
        if states.get(protocol) in _LEGACY_REPAIR_STATES
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

    # A partial encrypted credential is intentionally never auto-repaired. One
    # side may contain the only remaining stable identity, so regeneration could
    # silently rotate a live account. The admin must inspect that case manually.
    if partial:
        result["ok"] = False
        result["errors"].append(
            {
                "protocol": ",".join(partial),
                "error": "partial_credential_requires_manual_review",
            }
        )

    for protocol in candidates:
        db = SessionLocal()
        try:
            # Cross-process guard: serialize reconciliation for this subscription
            # using its database row. The lock is held only for one protocol.
            sub = (
                db.query(Subscription)
                .filter(Subscription.id == int(subscription_id))
                .with_for_update()
                .first()
            )
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

            if protocol not in _selected_modern_protocols(db, sub.id):
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
            current_state = _reconcile_credential_state(current)

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
                ad,
                db,
                sub,
                protocol,
                nodes,
            )

            if protocol_errors:
                result["ok"] = False
            for item in protocol_errors:
                result["errors"].append(dict(item))

            if not items:
                # _provision_modern_protocol may have created an in-memory empty
                # row. Never persist another placeholder when runtime repair did
                # not actually produce deliverable account material.
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
            if credential_state(credential) != "complete":
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
                quota_db,
                int(subscription_id),
            )
            if not result["quota"].get("ok"):
                result["ok"] = False
                result["errors"].append(
                    {
                        "protocol": "quota",
                        "error": "quota_sync_failed",
                    }
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


async def reconcile_subscription_modern_accounts(
    subscription_id: int,
    *,
    max_protocols: int | None = None,
) -> dict[str, Any]:
    async with _reconcile_lock:
        return await _reconcile_subscription_modern_accounts(
            subscription_id,
            max_protocols=max_protocols,
        )


def _next_scan_batch(limit: int = _BACKGROUND_SCAN_LIMIT) -> list[int]:
    global _scan_cursor

    db = SessionLocal()
    try:
        query = (
            db.query(Subscription.id)
            .join(
                SubscriptionProtocol,
                SubscriptionProtocol.subscription_id == Subscription.id,
            )
            .filter(
                Subscription.status == SubscriptionStatus.ACTIVE,
                SubscriptionProtocol.protocol.in_(MODERN_PROTOCOL_KEYS),
            )
            .distinct()
            .order_by(Subscription.id.asc())
        )

        rows = (
            query.filter(Subscription.id > int(_scan_cursor))
            .limit(max(1, int(limit)))
            .all()
        )
        if not rows:
            _scan_cursor = 0
            rows = query.limit(max(1, int(limit))).all()

        ids = [int(row[0]) for row in rows]
        if ids:
            _scan_cursor = ids[-1]
        return ids
    finally:
        db.close()


async def reconcile_legacy_modern_once() -> dict[str, Any] | None:
    async with _reconcile_lock:
        for subscription_id in _next_scan_batch():
            snapshot = _subscription_snapshot(subscription_id)
            if snapshot is None:
                continue
            states = dict(snapshot["states"])
            if not any(
                state in _LEGACY_REPAIR_STATES
                for state in states.values()
            ):
                continue

            return await _reconcile_subscription_modern_accounts(
                subscription_id,
                max_protocols=_BACKGROUND_MAX_PROTOCOLS,
            )
    return None


async def modern_legacy_reconcile_loop() -> None:
    """Bounded self-heal for legacy selected Modern credentials only."""

    await asyncio.sleep(_BACKGROUND_INITIAL_DELAY_SECONDS)
    while True:
        busy = False
        try:
            result = await reconcile_legacy_modern_once()
            if result is not None:
                busy = bool(result.get("repaired"))
                if result.get("repaired"):
                    logger.info(
                        "Modern legacy credential reconcile repaired subscription=%s protocols=%s",
                        result.get("subscription_id"),
                        [
                            item.get("protocol")
                            for item in result.get("repaired", [])
                            if isinstance(item, dict)
                        ],
                    )
                if result.get("errors"):
                    logger.warning(
                        "Modern legacy credential reconcile incomplete subscription=%s errors=%s",
                        result.get("subscription_id"),
                        result.get("errors"),
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Modern legacy credential reconcile cycle failed")

        await asyncio.sleep(
            _BACKGROUND_BUSY_SECONDS if busy else _BACKGROUND_IDLE_SECONDS
        )


@asynccontextmanager
async def _lifespan(_app):
    task = asyncio.create_task(
        modern_legacy_reconcile_loop(),
        name="modern-legacy-account-reconcile-v1",
    )
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


router = APIRouter(
    dependencies=[Depends(require_admin)],
    lifespan=_lifespan,
)


@router.post("/v1/subscriptions/{subscription_id}/reconcile-modern-accounts")
async def reconcile_modern_accounts_v1(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, int(subscription_id))
    if sub is None:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")
    if sub.status != SubscriptionStatus.ACTIVE:
        raise HTTPException(
            status_code=409,
            detail="فقط اشتراک فعال قابل Reconcile است",
        )

    return await reconcile_subscription_modern_accounts(subscription_id)
