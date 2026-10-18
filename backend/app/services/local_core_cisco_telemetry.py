from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..local_core_runtime import LOCAL_AGENT_URL
from ..models import Node, ProtocolCredential, SubscriptionNode
from ..quota_models import QuotaCursor, QuotaSession
from ..quota_schemas import SessionCloseIn, SessionOpenIn, UsageEventIn
from ..quota_service import close_session
from .quota_node_sync import ensure_protocol_quota_device
from .reseller_traffic_pool import apply_usage_event, open_session


log = logging.getLogger(__name__)
POLL_SECONDS = 3.0
SESSION_PREFIX = "ocserv"


def _field(row: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if name in row:
            return row[name]
        value = lowered.get(name.strip().lower())
        if value is not None:
            return value
    return None


def _counter_bytes(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(int(value), 0)

    text = str(value).strip().replace(",", "")
    if not text:
        return 0
    try:
        return max(int(float(text)), 0)
    except ValueError:
        pass

    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?i?b)", text, re.I)
    if not match:
        return 0
    amount = float(match.group(1))
    unit = match.group(2).lower()
    multiplier = {
        "b": 1,
        "kb": 1000,
        "kib": 1024,
        "mb": 1000**2,
        "mib": 1024**2,
        "gb": 1000**3,
        "gib": 1024**3,
        "tb": 1000**4,
        "tib": 1024**4,
    }.get(unit, 1)
    return max(int(amount * multiplier), 0)


def parse_occtl_users(raw: str) -> list[dict[str, Any]]:
    """Normalize ``occtl --json show users`` across ocserv JSON variants."""

    text = str(raw or "").strip()
    if not text:
        return []

    if "no users" in text.lower() and not text.startswith(("[", "{")):
        return []

    payload = json.loads(text)
    rows: list[Any]
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = []
        for key in ("users", "Users", "data", "sessions"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
        if not rows and payload and all(isinstance(value, dict) for value in payload.values()):
            rows = list(payload.values())
    else:
        rows = []

    result: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        username = str(
            _field(item, "Username", "username", "user", "User") or ""
        ).strip()
        if not username:
            continue

        runtime_id = str(
            _field(item, "ID", "id", "Session ID", "session_id") or ""
        ).strip()
        remote_ip = str(
            _field(item, "Remote IP", "remote_ip", "remote-ip", "remote") or ""
        ).strip()
        connected_at = str(
            _field(
                item,
                "raw_connected_at",
                "connected_at",
                "Connected at",
                "Connected At",
                "Since",
            )
            or ""
        ).strip()

        if not runtime_id:
            runtime_id = hashlib.sha256(
                f"{username}|{remote_ip}|{connected_at}".encode("utf-8")
            ).hexdigest()[:16]

        result.append(
            {
                "runtime_id": runtime_id[:48],
                "username": username,
                "remote_ip": remote_ip[:64] or None,
                "connected_at": connected_at[:96],
                "rx_bytes": _counter_bytes(
                    _field(item, "RX", "rx", "rx_bytes", "Bytes In", "bytes_in")
                ),
                "tx_bytes": _counter_bytes(
                    _field(item, "TX", "tx", "tx_bytes", "Bytes Out", "bytes_out")
                ),
            }
        )
    return result


def read_ocserv_snapshot() -> tuple[bool, list[dict[str, Any]], str | None]:
    try:
        process = subprocess.run(
            ["occtl", "--json", "show", "users"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, [], str(exc)

    output = (process.stdout or "").strip()
    error = (process.stderr or "").strip()
    if process.returncode != 0:
        return False, [], (error or output or f"occtl_exit_{process.returncode}")[:500]

    try:
        return True, parse_occtl_users(output), None
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return False, [], f"occtl_json_invalid:{exc}"[:500]


def _credential_map(db: Session, node_id: int) -> dict[str, ProtocolCredential]:
    rows = (
        db.query(ProtocolCredential, SubscriptionNode)
        .join(
            SubscriptionNode,
            SubscriptionNode.subscription_id == ProtocolCredential.subscription_id,
        )
        .filter(
            SubscriptionNode.node_id == node_id,
            ProtocolCredential.is_active.is_(True),
            ProtocolCredential.protocol.in_(["cisco", "openconnect"]),
        )
        .all()
    )

    grouped: dict[str, list[ProtocolCredential]] = {}
    for credential, _link in rows:
        username = str(credential.username or "").strip()
        if username:
            grouped.setdefault(username, []).append(credential)

    # Never guess when two subscriptions expose the same Cisco username.
    return {username: values[0] for username, values in grouped.items() if len(values) == 1}


def _runtime_id_from_key(session_key: str) -> str | None:
    parts = str(session_key or "").split(":", 3)
    if len(parts) < 4 or parts[0] != SESSION_PREFIX:
        return None
    return parts[2]


def _existing_session_key(
    db: Session,
    node_id: int,
    subscription_id: int,
    runtime_id: str,
) -> str | None:
    prefix = f"{SESSION_PREFIX}:{node_id}:{runtime_id}:"
    row = (
        db.query(QuotaSession)
        .filter(
            QuotaSession.node_id == node_id,
            QuotaSession.subscription_id == subscription_id,
            QuotaSession.protocol == "openconnect",
            QuotaSession.status == "active",
            QuotaSession.session_key.like(prefix + "%"),
        )
        .order_by(QuotaSession.id.desc())
        .first()
    )
    return str(row.session_key) if row else None


def _new_session_key(node_id: int, row: dict[str, Any]) -> str:
    runtime_id = str(row["runtime_id"])
    seed = "|".join(
        [
            str(row.get("username") or ""),
            str(row.get("remote_ip") or ""),
            str(row.get("connected_at") or ""),
            datetime.now(timezone.utc).isoformat(),
        ]
    )
    suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"{SESSION_PREFIX}:{node_id}:{runtime_id}:{suffix}"[:160]


def _close_missing_runtime_ids(
    db: Session,
    node_id: int,
    runtime_ids: set[str],
) -> int:
    closed = 0
    active = (
        db.query(QuotaSession)
        .filter(
            QuotaSession.node_id == node_id,
            QuotaSession.protocol == "openconnect",
            QuotaSession.status == "active",
        )
        .all()
    )
    for session in active:
        runtime_id = _runtime_id_from_key(session.session_key)
        if runtime_id is not None and runtime_id in runtime_ids:
            continue
        close_session(
            db,
            node_id,
            SessionCloseIn(session_key=session.session_key, reason="ocserv_disconnect"),
        )
        closed += 1
    return closed


def reconcile_cisco_snapshot(
    db: Session,
    node_id: int,
    observed: list[dict[str, Any]],
) -> dict[str, int]:
    """Map real ocserv sessions into quota sessions and the append-only ledger."""

    credential_by_username = _credential_map(db, node_id)
    runtime_ids = {str(item.get("runtime_id") or "") for item in observed}
    runtime_ids.discard("")

    # Close vanished sessions before opening replacements so a reconnect does not
    # briefly trip the concurrent-device limit on the same subscription.
    closed = _close_missing_runtime_ids(db, node_id, runtime_ids)

    opened = 0
    usage_events = 0
    matched_keys: set[str] = set()
    now_naive = datetime.utcnow()

    for row in observed:
        username = str(row.get("username") or "").strip()
        credential = credential_by_username.get(username)
        if credential is None:
            continue

        device = ensure_protocol_quota_device(db, credential)
        if device.status != "active":
            continue

        runtime_id = str(row.get("runtime_id") or "").strip()
        if not runtime_id:
            continue

        session_key = _existing_session_key(
            db,
            node_id,
            int(credential.subscription_id),
            runtime_id,
        )
        if session_key is None:
            session_key = _new_session_key(node_id, row)
            open_session(
                db,
                node_id,
                SessionOpenIn(
                    session_key=session_key,
                    subscription_id=int(credential.subscription_id),
                    device_id=int(device.id),
                    protocol="openconnect",
                    client_ip=row.get("remote_ip"),
                ),
            )
            opened += 1

        matched_keys.add(session_key)
        vpn_session = (
            db.query(QuotaSession)
            .filter(
                QuotaSession.node_id == node_id,
                QuotaSession.session_key == session_key,
            )
            .first()
        )
        if vpn_session is not None:
            vpn_session.last_seen_at = now_naive

        rx = max(int(row.get("rx_bytes") or 0), 0)
        tx = max(int(row.get("tx_bytes") or 0), 0)
        if rx + tx <= 0:
            continue

        source_key = f"ocserv:{node_id}:{session_key}"[:220]
        epoch = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:24]
        cursor = (
            db.query(QuotaCursor)
            .filter(
                QuotaCursor.node_id == node_id,
                QuotaCursor.source_key == source_key,
            )
            .first()
        )
        if cursor and cursor.counter_epoch == epoch:
            if rx == int(cursor.last_uplink_value) and tx == int(cursor.last_downlink_value):
                continue
            if rx < int(cursor.last_uplink_value) or tx < int(cursor.last_downlink_value):
                log.warning(
                    "local ocserv counters decreased; skipping sample node=%s session=%s",
                    node_id,
                    session_key,
                )
                continue

        sequence = max(rx + tx, 1)
        event_id = hashlib.sha256(
            f"{node_id}|{session_key}|{epoch}|{rx}|{tx}".encode("utf-8")
        ).hexdigest()
        apply_usage_event(
            db,
            node_id,
            UsageEventIn(
                event_id=event_id,
                subscription_id=int(credential.subscription_id),
                device_id=int(device.id),
                session_key=session_key,
                protocol="openconnect",
                source_key=source_key,
                counter_mode="cumulative",
                counter_epoch=epoch,
                source_sequence=sequence,
                uplink_value=rx,
                downlink_value=tx,
                reported_at=datetime.now(timezone.utc),
            ),
        )
        usage_events += 1

    # A successfully parsed snapshot is authoritative. Close active accounting
    # sessions that no longer map to a visible, uniquely-owned Cisco identity.
    active = (
        db.query(QuotaSession)
        .filter(
            QuotaSession.node_id == node_id,
            QuotaSession.protocol == "openconnect",
            QuotaSession.status == "active",
        )
        .all()
    )
    for session in active:
        if session.session_key in matched_keys:
            continue
        close_session(
            db,
            node_id,
            SessionCloseIn(session_key=session.session_key, reason="ocserv_identity_missing"),
        )
        closed += 1

    return {"opened": opened, "usage_events": usage_events, "closed": closed}


def collect_local_core_cisco_once() -> dict[str, Any]:
    db = SessionLocal()
    try:
        node = (
            db.query(Node)
            .filter(
                Node.retired_at.is_(None),
                Node.agent_url == LOCAL_AGENT_URL,
            )
            .order_by(Node.id.asc())
            .first()
        )
        if node is None:
            return {"ok": True, "skipped": "local_core_missing"}

        ok, observed, error = read_ocserv_snapshot()
        if not ok:
            db.rollback()
            return {"ok": False, "error": error or "occtl_failed"}

        result = reconcile_cisco_snapshot(db, int(node.id), observed)
        db.commit()
        return {"ok": True, "observed": len(observed), **result}
    except Exception as exc:
        db.rollback()
        log.exception("local core Cisco telemetry failed")
        return {"ok": False, "error": str(exc)[:500]}
    finally:
        db.close()


async def local_core_cisco_telemetry_loop() -> None:
    """Continuously mirror Local Core ocserv state into TwinPanel Quota Core."""

    while True:
        try:
            await asyncio.to_thread(collect_local_core_cisco_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("local core Cisco telemetry loop failed")
        await asyncio.sleep(POLL_SECONDS)
