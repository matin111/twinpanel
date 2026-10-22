from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_

from ..database import SessionLocal
from ..models import Node, NodeProtocolConfig, ProtocolCredential
from ..quota_models import QuotaNodeCommand
from .. import subscription_enforcement as enforcement


logger = logging.getLogger(__name__)

SINGBOX_MODERN_PROTOCOLS = frozenset(
    {"hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell"}
)
STANDALONE_MODERN_PROTOCOLS = frozenset(
    {"mieru", "trusttunnel", "amneziawg", "sudoku"}
)
CONTROLLER_MODERN_PROTOCOLS = SINGBOX_MODERN_PROTOCOLS | STANDALONE_MODERN_PROTOCOLS

_EXECUTOR = "controller-modern-v1"
_PROCESSING_TIMEOUT_SECONDS = 90
_MAX_ATTEMPTS = 5
_installed = False
_original_queue = None


def _command_protocol(command: QuotaNodeCommand) -> str:
    payload = command.payload if isinstance(command.payload, dict) else {}
    return str(payload.get("protocol") or "").strip().lower()


def install_modern_enforcement_hooks() -> None:
    """Route all Modern account enforcement to the controller worker."""

    global _installed, _original_queue
    if _installed:
        return

    enforcement.AGENT_PROTOCOL.update(
        {protocol: protocol for protocol in CONTROLLER_MODERN_PROTOCOLS}
    )
    enforcement.SESSION_ALIASES.update(
        {protocol: {protocol} for protocol in CONTROLLER_MODERN_PROTOCOLS}
    )

    original = enforcement.queue_subscription_enforcement
    _original_queue = original

    def controller_aware_queue(
        db,
        subscription,
        *,
        command_type: str,
        reason: str,
        protocols: list[str] | None = None,
        node_ids: list[int] | None = None,
    ) -> dict:
        result = original(
            db,
            subscription,
            command_type=command_type,
            reason=reason,
            protocols=protocols,
            node_ids=node_ids,
        )

        command_ids = [
            str(item.get("command_id") or "")
            for item in result.get("commands", [])
            if item.get("command_id")
        ]
        if not command_ids:
            return result

        db.flush()
        rows = (
            db.query(QuotaNodeCommand)
            .filter(QuotaNodeCommand.command_id.in_(command_ids))
            .all()
        )
        for row in rows:
            protocol = _command_protocol(row)
            if protocol not in CONTROLLER_MODERN_PROTOCOLS:
                continue
            payload = dict(row.payload or {})
            payload["executor"] = _EXECUTOR
            row.payload = payload
            # Agent pull only consumes status=pending. Controller-owned Modern
            # work is durable and cannot race a legacy node Agent.
            row.status = "controller_pending"

        return result

    enforcement.queue_subscription_enforcement = controller_aware_queue
    _installed = True


def _claim_next_command() -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        stale_before = now - timedelta(seconds=_PROCESSING_TIMEOUT_SECONDS)
        row = (
            db.query(QuotaNodeCommand)
            .filter(
                QuotaNodeCommand.expires_at > now,
                or_(
                    QuotaNodeCommand.status == "controller_pending",
                    and_(
                        QuotaNodeCommand.status == "controller_processing",
                        QuotaNodeCommand.last_delivered_at.isnot(None),
                        QuotaNodeCommand.last_delivered_at < stale_before,
                    ),
                ),
            )
            .order_by(QuotaNodeCommand.issued_at.asc())
            .with_for_update(skip_locked=True)
            .first()
        )
        if row is None:
            db.rollback()
            return None

        protocol = _command_protocol(row)
        payload = dict(row.payload or {})
        if (
            protocol not in CONTROLLER_MODERN_PROTOCOLS
            or payload.get("executor") != _EXECUTOR
        ):
            row.status = "failed"
            row.result_code = "controller_protocol_mismatch"
            row.result_message = "command is not owned by Modern controller"
            row.acknowledged_at = now
            db.commit()
            return None

        row.status = "controller_processing"
        row.attempt_count = int(row.attempt_count or 0) + 1
        row.last_delivered_at = now
        snapshot = {
            "command_id": str(row.command_id),
            "node_id": int(row.node_id),
            "command_type": str(row.command_type),
            "subscription_id": int(payload.get("subscription_id") or 0),
            "protocol": protocol,
            "attempt": int(row.attempt_count),
        }
        db.commit()
        return snapshot
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _decode_stored_secret(protocol: str, credential: ProtocolCredential):
    from ..routers import account_delivery as account_delivery

    decoded = account_delivery._dec(credential.secret_encrypted)
    if not isinstance(decoded, dict):
        raise RuntimeError("stored protocol credential is invalid")

    if protocol in SINGBOX_MODERN_PROTOCOLS:
        from ..singbox_subscription_accounts import secret_from_dict
    else:
        from ..standalone_subscription_accounts import secret_from_dict

    secret = secret_from_dict(decoded)
    if str(secret.protocol) != protocol:
        raise RuntimeError("stored protocol credential protocol mismatch")
    return secret


async def _execute_command(command: dict[str, Any]) -> None:
    command_id = str(command["command_id"])
    protocol = str(command["protocol"])
    subscription_id = int(command["subscription_id"])
    node_id = int(command["node_id"])
    command_type = str(command["command_type"])

    db = SessionLocal()
    conn = None
    error: Exception | None = None
    result_code = "controller_modern_applied"
    try:
        if subscription_id <= 0:
            raise RuntimeError("subscription_id is missing")

        node = db.get(Node, node_id)
        if node is None or getattr(node, "retired_at", None) is not None:
            raise RuntimeError("exit node is unavailable")

        credential = (
            db.query(ProtocolCredential)
            .filter(
                ProtocolCredential.subscription_id == subscription_id,
                ProtocolCredential.protocol == protocol,
            )
            .first()
        )
        if credential is None or not credential.secret_encrypted:
            raise RuntimeError("protocol credential is unavailable")

        from ..routers.provision import ssh_connect_saved

        secret = _decode_stored_secret(protocol, credential)
        conn = await ssh_connect_saved(node, db)

        if protocol in SINGBOX_MODERN_PROTOCOLS:
            from ..singbox_subscription_accounts import apply_account, remove_account

            if command_type == "revoke_subscription":
                await remove_account(conn, protocol, subscription_id)
                result_code = "controller_modern_revoked"
            elif command_type == "restore_subscription":
                if not bool(credential.is_active):
                    raise RuntimeError("active protocol credential is unavailable")
                await apply_account(conn, node, secret)
                result_code = "controller_modern_restored"
            else:
                raise RuntimeError(f"unsupported command type: {command_type}")
        else:
            from ..standalone_subscription_accounts import apply_account, remove_account

            if command_type == "revoke_subscription":
                await remove_account(conn, secret)
                result_code = "controller_standalone_revoked"
            elif command_type == "restore_subscription":
                if not bool(credential.is_active):
                    raise RuntimeError("active protocol credential is unavailable")
                cfg = (
                    db.query(NodeProtocolConfig)
                    .filter(
                        NodeProtocolConfig.node_id == node_id,
                        NodeProtocolConfig.protocol == protocol,
                        NodeProtocolConfig.status == "online",
                    )
                    .first()
                )
                if cfg is None or not cfg.port:
                    raise RuntimeError("standalone runtime config is unavailable")
                await apply_account(conn, node, secret, int(cfg.port))
                result_code = "controller_standalone_restored"
            else:
                raise RuntimeError(f"unsupported command type: {command_type}")

    except Exception as exc:
        error = exc
    finally:
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:
                pass
        db.close()

    status_db = SessionLocal()
    try:
        row = (
            status_db.query(QuotaNodeCommand)
            .filter(QuotaNodeCommand.command_id == command_id)
            .with_for_update()
            .first()
        )
        if row is None:
            status_db.rollback()
            return

        now = datetime.utcnow()
        if error is None:
            row.status = "succeeded"
            row.result_code = result_code
            row.result_message = None
            row.acknowledged_at = now
        else:
            message = f"{type(error).__name__}:{str(error)[:700]}"
            if int(row.attempt_count or 0) >= _MAX_ATTEMPTS or row.expires_at <= now:
                row.status = "failed"
                row.acknowledged_at = now
                row.result_code = "controller_modern_failed"
            else:
                row.status = "controller_pending"
                row.result_code = "controller_modern_retry"
            row.result_message = message
        status_db.commit()
    except Exception:
        status_db.rollback()
        raise
    finally:
        status_db.close()


async def process_modern_enforcement_once(*, limit: int = 20) -> int:
    processed = 0
    for _ in range(max(1, min(int(limit), 100))):
        command = _claim_next_command()
        if command is None:
            break
        await _execute_command(command)
        processed += 1
    return processed


async def modern_enforcement_loop() -> None:
    """Durable controller-side worker for all Modern revoke/restore commands."""

    install_modern_enforcement_hooks()
    while True:
        processed = 0
        try:
            processed = await process_modern_enforcement_once(limit=20)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Modern enforcement worker cycle failed")
        await asyncio.sleep(0.5 if processed else 3.0)
