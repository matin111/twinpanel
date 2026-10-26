from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import re
import shlex
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_

from ..database import SessionLocal
from ..models import Node, NodeType, Subscription
from ..node_runtime_connection import connect_protocol_runtime
from ..quota_models import QuotaCursor, QuotaSession
from ..quota_schemas import SessionCloseIn, SessionOpenIn, UsageEventIn
from ..quota_service import close_session
from .quota_node_sync import build_node_devices
from .reseller_traffic_pool import apply_usage_event, open_session


MODERN_ACCOUNTING_INTERVAL_SECONDS = 5.0
PRESENCE_STALE_SECONDS = 45
WIREGUARD_HANDSHAKE_STALE_SECONDS = 180
MODERN_ACCOUNTING_LOCK = Path("/run/twinpanel-modern-quota.lock")

# Capabilities are explicit and fail closed. A protocol is never marked as
# traffic-accounting-ready until TwinPanel has a verified cumulative per-user
# source. Presence-only protocols never fabricate byte counters.
TRAFFIC_ACCOUNTING_PROTOCOLS = frozenset(
    {"wireguard", "amneziawg", "trusttunnel"}
)
PRESENCE_ACCOUNTING_PROTOCOLS = frozenset(
    {"wireguard", "amneziawg", "trusttunnel", "mieru", "sudoku"}
)

_EPOCH_MARKER = "__TWINPANEL_COUNTER_EPOCH__"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _safe_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _short_epoch(value: str, *, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) < 8:
        text = f"{fallback}:{text or 'unknown'}"
    if len(text) <= 96:
        return text
    digest = hashlib.sha256(text.encode()).hexdigest()[:24]
    return f"{text[:68]}:{digest}"[:96]


def _normalize_ip_or_network(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "," in text:
        text = text.split(",", 1)[0].strip()
    return text.split("/", 1)[0].strip()


async def _run_node_command(
    conn,
    script: str,
    *,
    timeout: float = 10.0,
) -> tuple[bool, str]:
    try:
        result = await conn.run(
            "bash -lc " + shlex.quote(script),
            check=False,
            timeout=timeout,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}:{exc}"

    output = (
        str(getattr(result, "stdout", "") or "")
        + (
            "\n" + str(getattr(result, "stderr", "") or "")
            if getattr(result, "stderr", "")
            else ""
        )
    ).strip()
    return int(getattr(result, "exit_status", 1)) == 0, output


def _devices_by_protocol(db, node_id: int) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in build_node_devices(db, int(node_id)):
        protocol = str(item.get("protocol") or "").strip().lower()
        if protocol not in PRESENCE_ACCOUNTING_PROTOCOLS:
            continue
        grouped.setdefault(protocol, []).append(dict(item))
    return grouped


def _active_sessions(
    db,
    *,
    node_id: int,
    device_id: int,
    protocol: str,
) -> list[QuotaSession]:
    return (
        db.query(QuotaSession)
        .filter(
            QuotaSession.node_id == int(node_id),
            QuotaSession.device_id == int(device_id),
            QuotaSession.protocol == protocol,
            QuotaSession.status == "active",
        )
        .order_by(QuotaSession.id.asc())
        .all()
    )


def _session_key(
    *,
    node_id: int,
    device_id: int,
    protocol: str,
    evidence: str,
) -> str:
    digest = hashlib.sha256(
        f"{node_id}:{device_id}:{protocol}:{evidence}:{time.time_ns()}".encode()
    ).hexdigest()[:24]
    return f"runtime:{protocol}:{node_id}:{device_id}:{digest}"[:160]


def _mark_presence(
    db,
    *,
    node_id: int,
    device: dict[str, Any],
    protocol: str,
    online: bool,
    observed_at: datetime,
    client_ip: str | None,
    evidence: str,
) -> dict[str, int]:
    """Open/touch/close canonical sessions from authoritative presence."""

    device_id = int(device["device_id"])
    sessions = _active_sessions(
        db,
        node_id=node_id,
        device_id=device_id,
        protocol=protocol,
    )
    opened = 0
    closed = 0

    if online:
        if not sessions:
            result = open_session(
                db,
                int(node_id),
                SessionOpenIn(
                    session_key=_session_key(
                        node_id=int(node_id),
                        device_id=device_id,
                        protocol=protocol,
                        evidence=evidence,
                    ),
                    subscription_id=int(device["subscription_id"]),
                    device_id=device_id,
                    protocol=protocol,
                    client_ip=(str(client_ip).strip()[:64] if client_ip else None),
                ),
            )
            opened = 0 if bool(result.get("duplicate")) else 1
            sessions = _active_sessions(
                db,
                node_id=node_id,
                device_id=device_id,
                protocol=protocol,
            )

        last_seen = _naive(observed_at)
        for row in sessions:
            if last_seen > row.last_seen_at:
                row.last_seen_at = last_seen
            if client_ip:
                row.client_ip = str(client_ip).strip()[:64]
        return {"opened": opened, "closed": 0}

    for row in sessions:
        close_session(
            db,
            int(node_id),
            SessionCloseIn(
                session_key=row.session_key,
                reason="runtime_presence_ended",
            ),
        )
        closed += 1
    return {"opened": 0, "closed": closed}


def _activate_from_real_usage_if_needed(
    db,
    *,
    node_id: int,
    device: dict[str, Any],
    protocol: str,
    client_ip: str | None,
    evidence: str,
) -> bool:
    """Start first-use only when a positive real runtime delta proves traffic."""

    subscription = db.get(Subscription, int(device["subscription_id"]))
    if subscription is None:
        return False
    if subscription.starts_at is not None or subscription.expires_at is not None:
        return False

    if _active_sessions(
        db,
        node_id=int(node_id),
        device_id=int(device["device_id"]),
        protocol=protocol,
    ):
        return False

    key = _session_key(
        node_id=int(node_id),
        device_id=int(device["device_id"]),
        protocol=protocol,
        evidence=f"usage:{evidence}",
    )
    open_session(
        db,
        int(node_id),
        SessionOpenIn(
            session_key=key,
            subscription_id=int(device["subscription_id"]),
            device_id=int(device["device_id"]),
            protocol=protocol,
            client_ip=(str(client_ip).strip()[:64] if client_ip else None),
        ),
    )
    close_session(
        db,
        int(node_id),
        SessionCloseIn(
            session_key=key,
            reason="runtime_usage_proved_connection",
        ),
    )
    return True


def _baseline_or_apply_cumulative(
    db,
    *,
    node_id: int,
    device: dict[str, Any],
    protocol: str,
    source_key: str,
    counter_epoch: str,
    uplink: int,
    downlink: int,
    session_key: str | None,
    client_ip: str | None,
    reported_at: datetime,
) -> dict[str, Any]:
    """Safely feed a real cumulative runtime counter into the quota ledger.

    The first observation is a non-billable baseline so rollout cannot charge
    traffic that happened before this collector existed. Counter decreases are
    rejected unless the runtime itself supplied a new epoch. Collector restarts
    therefore cannot replay usage, while genuine runtime/interface restarts are
    accepted through their authoritative epoch marker.
    """

    source_key = str(source_key)[:220]
    epoch = _short_epoch(counter_epoch, fallback=f"{protocol}:{node_id}")
    uplink = max(int(uplink), 0)
    downlink = max(int(downlink), 0)
    sequence = min(int(time.time_ns()), 2**63 - 1)

    cursor = (
        db.query(QuotaCursor)
        .filter(
            QuotaCursor.node_id == int(node_id),
            QuotaCursor.source_key == source_key,
        )
        .first()
    )

    if cursor is None:
        db.add(
            QuotaCursor(
                node_id=int(node_id),
                subscription_id=int(device["subscription_id"]),
                device_id=int(device["device_id"]),
                protocol=protocol,
                source_key=source_key,
                counter_mode="cumulative",
                counter_epoch=epoch,
                last_sequence=sequence,
                last_uplink_value=uplink,
                last_downlink_value=downlink,
                updated_at=_naive(reported_at),
            )
        )
        db.flush()
        return {
            "baselined": True,
            "event": False,
            "accepted_bytes": 0,
            "epoch_changed": False,
        }

    if (
        cursor.subscription_id != int(device["subscription_id"])
        or cursor.device_id != int(device["device_id"])
        or str(cursor.protocol) != protocol
    ):
        raise RuntimeError("runtime_counter_source_identity_conflict")

    same_epoch = str(cursor.counter_epoch) == epoch
    if same_epoch and (
        uplink < int(cursor.last_uplink_value)
        or downlink < int(cursor.last_downlink_value)
    ):
        raise RuntimeError("counter_decreased_without_authoritative_new_epoch")

    if (
        same_epoch
        and uplink == int(cursor.last_uplink_value)
        and downlink == int(cursor.last_downlink_value)
    ):
        cursor.updated_at = _naive(reported_at)
        return {
            "baselined": False,
            "event": False,
            "accepted_bytes": 0,
            "epoch_changed": False,
        }

    proven_bytes = (
        max(uplink - int(cursor.last_uplink_value), 0)
        + max(downlink - int(cursor.last_downlink_value), 0)
        if same_epoch
        else uplink + downlink
    )

    if proven_bytes > 0:
        _activate_from_real_usage_if_needed(
            db,
            node_id=int(node_id),
            device=device,
            protocol=protocol,
            client_ip=client_ip,
            evidence=f"{source_key}:{epoch}",
        )

    event_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            (
                f"twinpanel:modern-runtime:{node_id}:{source_key}:{epoch}:"
                f"{sequence}:{uplink}:{downlink}"
            ),
        )
    )
    result = apply_usage_event(
        db,
        int(node_id),
        UsageEventIn(
            event_id=event_id,
            subscription_id=int(device["subscription_id"]),
            device_id=int(device["device_id"]),
            session_key=session_key,
            protocol=protocol,
            source_key=source_key,
            counter_mode="cumulative",
            counter_epoch=epoch,
            source_sequence=sequence,
            uplink_value=uplink,
            downlink_value=downlink,
            reported_at=reported_at,
        ),
    )
    return {
        "baselined": False,
        "event": True,
        "accepted_bytes": max(int(result.get("accepted_bytes") or 0), 0),
        "epoch_changed": not same_epoch,
    }


def _parse_dump(raw: str) -> tuple[str, list[dict[str, Any]]]:
    epoch = ""
    lines: list[str] = []
    for line in str(raw or "").splitlines():
        if line.startswith(_EPOCH_MARKER):
            epoch = line[len(_EPOCH_MARKER) :].strip()
        elif line.strip():
            lines.append(line.rstrip())

    if not epoch:
        raise ValueError("counter_epoch_missing")
    if not lines:
        return epoch, []

    peers: list[dict[str, Any]] = []
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) < 8:
            fields = line.split()
        if len(fields) < 8:
            continue
        peers.append(
            {
                "public_key": fields[0].strip(),
                "endpoint": fields[2].strip(),
                "allowed_ips": [
                    item.strip() for item in fields[3].split(",") if item.strip()
                ],
                "latest_handshake": _safe_int(fields[4]),
                "rx": _safe_int(fields[5]),
                "tx": _safe_int(fields[6]),
            }
        )
    return epoch, peers


async def _collect_wireguard_like(
    conn,
    *,
    binary: str,
    interface: str,
) -> tuple[bool, str, list[dict[str, Any]], str | None]:
    script = f"""set -eu
command -v {shlex.quote(binary)} >/dev/null
test -r /sys/class/net/{shlex.quote(interface)}/ifindex
boot="$(cat /proc/sys/kernel/random/boot_id)"
ifindex="$(cat /sys/class/net/{shlex.quote(interface)}/ifindex)"
printf '{_EPOCH_MARKER}%s:%s\\n' "$boot" "$ifindex"
{shlex.quote(binary)} show {shlex.quote(interface)} dump
"""
    ok, output = await _run_node_command(conn, script, timeout=8)
    if not ok:
        return False, "", [], output[-600:]
    try:
        epoch, peers = _parse_dump(output)
    except Exception as exc:
        return False, "", [], f"dump_parse_failed:{exc}"
    return True, epoch, peers, None


def _peer_for_wireguard_identity(
    peers: list[dict[str, Any]],
    identity: str,
) -> dict[str, Any] | None:
    wanted = _normalize_ip_or_network(identity)
    if not wanted:
        return None
    for peer in peers:
        networks = {
            _normalize_ip_or_network(item) for item in peer.get("allowed_ips") or []
        }
        if wanted in networks:
            return peer
    return None


def _peer_for_public_key(
    peers: list[dict[str, Any]],
    identity: str,
) -> dict[str, Any] | None:
    wanted = str(identity or "").strip()
    if not wanted:
        return None
    for peer in peers:
        if str(peer.get("public_key") or "").strip() == wanted:
            return peer
    return None


def _endpoint_ip(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text == "(none)":
        return None
    if text.startswith("[") and "]" in text:
        return text[1 : text.index("]")]
    if ":" in text:
        return text.rsplit(":", 1)[0]
    return text


def _apply_wireguard_like(
    db,
    *,
    node: Node,
    protocol: str,
    devices: list[dict[str, Any]],
    epoch: str,
    peers: list[dict[str, Any]],
    match_by_key: bool,
) -> dict[str, Any]:
    now = _utcnow()
    now_ts = int(now.timestamp())
    matched = online_count = opened = closed = 0
    baselined = usage_events = accepted_bytes = epoch_changes = 0

    for device in devices:
        identity = str(
            device.get("telemetry_identity") or device.get("identity") or ""
        ).strip()
        peer = (
            _peer_for_public_key(peers, identity)
            if match_by_key
            else _peer_for_wireguard_identity(peers, identity)
        )
        if peer is None:
            presence = _mark_presence(
                db,
                node_id=int(node.id),
                device=device,
                protocol=protocol,
                online=False,
                observed_at=now,
                client_ip=None,
                evidence=f"{identity}:missing",
            )
            closed += presence["closed"]
            continue

        matched += 1
        handshake = _safe_int(peer.get("latest_handshake"))
        online = bool(
            handshake > 0
            and now_ts >= handshake
            and now_ts - handshake <= WIREGUARD_HANDSHAKE_STALE_SECONDS
        )
        client_ip = _endpoint_ip(peer.get("endpoint"))

        # The authoritative handshake decides whether the peer is live. Once it
        # is inside the freshness window, each successful collector poll touches
        # last_seen_at with the poll time so the canonical session does not go
        # stale merely because WireGuard did not need another handshake yet.
        presence = _mark_presence(
            db,
            node_id=int(node.id),
            device=device,
            protocol=protocol,
            online=online,
            observed_at=now,
            client_ip=client_ip,
            evidence=f"{identity}:handshake={handshake}",
        )
        opened += presence["opened"]
        closed += presence["closed"]
        online_count += int(online)

        active = _active_sessions(
            db,
            node_id=int(node.id),
            device_id=int(device["device_id"]),
            protocol=protocol,
        )
        source_identity = str(peer.get("public_key") or identity).strip()
        usage = _baseline_or_apply_cumulative(
            db,
            node_id=int(node.id),
            device=device,
            protocol=protocol,
            source_key=f"{protocol}:{source_identity}"[:220],
            counter_epoch=epoch,
            uplink=_safe_int(peer.get("rx")),
            downlink=_safe_int(peer.get("tx")),
            session_key=(active[0].session_key if active else None),
            client_ip=client_ip,
            reported_at=now,
        )
        baselined += int(bool(usage["baselined"]))
        usage_events += int(bool(usage["event"]))
        accepted_bytes += int(usage["accepted_bytes"])
        epoch_changes += int(bool(usage["epoch_changed"]))

    return {
        "collector": protocol,
        "node_id": int(node.id),
        "targets": len(devices),
        "matched": matched,
        "online": online_count,
        "opened": opened,
        "closed": closed,
        "baselined": baselined,
        "usage_events": usage_events,
        "accepted_bytes": accepted_bytes,
        "epoch_changes": epoch_changes,
    }


def _parse_trusttunnel_clients(raw: str) -> tuple[str, list[dict[str, Any]]]:
    epoch = ""
    json_lines: list[str] = []
    for line in str(raw or "").splitlines():
        if line.startswith(_EPOCH_MARKER):
            epoch = line[len(_EPOCH_MARKER) :].strip()
        else:
            json_lines.append(line)
    if not epoch:
        raise ValueError("trusttunnel_epoch_missing")

    payload = json.loads("\n".join(json_lines).strip() or "[]")
    if not isinstance(payload, list):
        raise ValueError("trusttunnel_clients_not_list")

    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        username = str(item.get("username") or "").strip()
        if not username:
            continue
        rows.append(
            {
                "username": username,
                "ip": str(item.get("ip") or "").strip() or None,
                "sessions": _safe_int(item.get("sessions")),
                "inbound": _safe_int(item.get("inbound")),
                "outbound": _safe_int(item.get("outbound")),
            }
        )
    return epoch, rows


async def _collect_trusttunnel(
    conn,
) -> tuple[bool, str, list[dict[str, Any]], str | None]:
    script = f"""set -eu
epoch="$(systemctl show twinpanel-trusttunnel.service -p ActiveEnterTimestampMonotonic --value 2>/dev/null || true)"
if [ -z "$epoch" ]; then
  pid="$(systemctl show twinpanel-trusttunnel.service -p MainPID --value 2>/dev/null || true)"
  if [ -n "$pid" ] && [ "$pid" != "0" ] && [ -r "/proc/$pid/stat" ]; then
    epoch="proc-$(awk '{{print $22}}' "/proc/$pid/stat")"
  fi
fi
[ -n "$epoch" ] || epoch=unknown
printf '{_EPOCH_MARKER}%s\\n' "$epoch"
curl -fsS --max-time 4 http://127.0.0.1:1987/clients
"""
    ok, output = await _run_node_command(conn, script, timeout=8)
    if not ok:
        return False, "", [], output[-600:]
    try:
        epoch, rows = _parse_trusttunnel_clients(output)
    except Exception as exc:
        return False, "", [], f"trusttunnel_parse_failed:{exc}"
    return True, epoch, rows, None


def _apply_trusttunnel(
    db,
    *,
    node: Node,
    devices: list[dict[str, Any]],
    epoch: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_user = {str(row["username"]): row for row in rows}
    now = _utcnow()
    matched = online_count = opened = closed = 0
    baselined = usage_events = accepted_bytes = epoch_changes = 0

    for device in devices:
        username = str(
            device.get("telemetry_identity") or device.get("identity") or ""
        ).strip()
        row = by_user.get(username)
        if row is None:
            presence = _mark_presence(
                db,
                node_id=int(node.id),
                device=device,
                protocol="trusttunnel",
                online=False,
                observed_at=now,
                client_ip=None,
                evidence=f"{username}:missing",
            )
            closed += presence["closed"]
            continue

        matched += 1
        online = int(row["sessions"]) > 0
        presence = _mark_presence(
            db,
            node_id=int(node.id),
            device=device,
            protocol="trusttunnel",
            online=online,
            observed_at=now,
            client_ip=row.get("ip"),
            evidence=f"{username}:sessions={row['sessions']}",
        )
        opened += presence["opened"]
        closed += presence["closed"]
        online_count += int(online)

        active = _active_sessions(
            db,
            node_id=int(node.id),
            device_id=int(device["device_id"]),
            protocol="trusttunnel",
        )
        usage = _baseline_or_apply_cumulative(
            db,
            node_id=int(node.id),
            device=device,
            protocol="trusttunnel",
            source_key=f"trusttunnel:{username}"[:220],
            counter_epoch=epoch,
            uplink=int(row["inbound"]),
            downlink=int(row["outbound"]),
            session_key=(active[0].session_key if active else None),
            client_ip=row.get("ip"),
            reported_at=now,
        )
        baselined += int(bool(usage["baselined"]))
        usage_events += int(bool(usage["event"]))
        accepted_bytes += int(usage["accepted_bytes"])
        epoch_changes += int(bool(usage["epoch_changed"]))

    return {
        "collector": "trusttunnel",
        "node_id": int(node.id),
        "targets": len(devices),
        "matched": matched,
        "online": online_count,
        "opened": opened,
        "closed": closed,
        "baselined": baselined,
        "usage_events": usage_events,
        "accepted_bytes": accepted_bytes,
        "epoch_changes": epoch_changes,
    }


def _parse_mieru_users(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in str(raw or "").splitlines():
        text = line.strip()
        if not text or text.lower().startswith("user "):
            continue
        fields = re.split(r"\s+", text)
        if len(fields) < 2:
            continue
        username = fields[0].strip()
        stamp = fields[1].strip()
        if not username or username.lower() == "user":
            continue
        try:
            last_active = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if last_active.tzinfo is None:
                last_active = last_active.replace(tzinfo=timezone.utc)
            last_active = last_active.astimezone(timezone.utc)
        except ValueError:
            continue
        rows.append({"username": username, "last_active": last_active})
    return rows


async def _collect_mieru(
    conn,
) -> tuple[bool, list[dict[str, Any]], str | None]:
    ok, output = await _run_node_command(conn, "mita get users", timeout=8)
    if not ok:
        return False, [], output[-600:]
    try:
        return True, _parse_mieru_users(output), None
    except Exception as exc:
        return False, [], f"mieru_parse_failed:{exc}"


def _apply_mieru_presence(
    db,
    *,
    node: Node,
    devices: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_user = {str(row["username"]): row for row in rows}
    now = _utcnow()
    opened = closed = online_count = matched = 0

    for device in devices:
        username = str(
            device.get("telemetry_identity") or device.get("identity") or ""
        ).strip()
        row = by_user.get(username)
        if row is None:
            presence = _mark_presence(
                db,
                node_id=int(node.id),
                device=device,
                protocol="mieru",
                online=False,
                observed_at=now,
                client_ip=None,
                evidence=f"{username}:missing",
            )
            closed += presence["closed"]
            continue

        matched += 1
        last_active = row["last_active"]
        age = (now - last_active).total_seconds()
        online = 0 <= age <= PRESENCE_STALE_SECONDS
        presence = _mark_presence(
            db,
            node_id=int(node.id),
            device=device,
            protocol="mieru",
            online=online,
            observed_at=now,
            client_ip=None,
            evidence=f"{username}:source-last-active={int(last_active.timestamp())}",
        )
        opened += presence["opened"]
        closed += presence["closed"]
        online_count += int(online)

    return {
        "collector": "mieru",
        "node_id": int(node.id),
        "targets": len(devices),
        "matched": matched,
        "online": online_count,
        "opened": opened,
        "closed": closed,
        "usage_events": 0,
        "usage_supported": False,
    }


def _sudoku_port(identity: str) -> int | None:
    match = re.search(r":(\d{1,5})$", str(identity or "").strip())
    if not match:
        return None
    port = int(match.group(1))
    return port if 1 <= port <= 65535 else None


async def _collect_established_tcp_ports(
    conn,
) -> tuple[bool, dict[int, int], str | None]:
    ok, output = await _run_node_command(
        conn,
        r"""set -eu
ss -H -tn state established | awk '{print $4}'
""",
        timeout=6,
    )
    if not ok:
        return False, {}, output[-600:]

    ports: dict[int, int] = {}
    for line in output.splitlines():
        text = line.strip()
        if not text or ":" not in text:
            continue
        try:
            port = int(text.rsplit(":", 1)[1])
        except ValueError:
            continue
        ports[port] = ports.get(port, 0) + 1
    return True, ports, None


def _apply_sudoku_presence(
    db,
    *,
    node: Node,
    devices: list[dict[str, Any]],
    established_ports: dict[int, int],
) -> dict[str, Any]:
    now = _utcnow()
    opened = closed = online_count = matched = 0

    for device in devices:
        identity = str(
            device.get("telemetry_identity") or device.get("identity") or ""
        ).strip()
        port = _sudoku_port(identity)
        if port is None:
            continue
        matched += 1
        online = established_ports.get(port, 0) > 0
        presence = _mark_presence(
            db,
            node_id=int(node.id),
            device=device,
            protocol="sudoku",
            online=online,
            observed_at=now,
            client_ip=None,
            evidence=f"{identity}:established={established_ports.get(port, 0)}",
        )
        opened += presence["opened"]
        closed += presence["closed"]
        online_count += int(online)

    return {
        "collector": "sudoku",
        "node_id": int(node.id),
        "targets": len(devices),
        "matched": matched,
        "online": online_count,
        "opened": opened,
        "closed": closed,
        "usage_events": 0,
        "usage_supported": False,
    }


async def _reconcile_node(db, node: Node) -> list[dict[str, Any]]:
    grouped = _devices_by_protocol(db, int(node.id))
    if not grouped:
        return []

    conn = None
    results: list[dict[str, Any]] = []
    try:
        conn = await connect_protocol_runtime(node, db)

        if grouped.get("wireguard"):
            ok, epoch, peers, error = await _collect_wireguard_like(
                conn,
                binary="wg",
                interface="wg-access0",
            )
            results.append(
                {
                    "ok": True,
                    **_apply_wireguard_like(
                        db,
                        node=node,
                        protocol="wireguard",
                        devices=grouped["wireguard"],
                        epoch=epoch,
                        peers=peers,
                        match_by_key=False,
                    ),
                }
                if ok
                else {
                    "ok": False,
                    "collector": "wireguard",
                    "node_id": int(node.id),
                    "error": error or "wireguard_source_unavailable",
                }
            )

        if grouped.get("amneziawg"):
            ok, epoch, peers, error = await _collect_wireguard_like(
                conn,
                binary="awg",
                interface="tpawg0",
            )
            results.append(
                {
                    "ok": True,
                    **_apply_wireguard_like(
                        db,
                        node=node,
                        protocol="amneziawg",
                        devices=grouped["amneziawg"],
                        epoch=epoch,
                        peers=peers,
                        match_by_key=True,
                    ),
                }
                if ok
                else {
                    "ok": False,
                    "collector": "amneziawg",
                    "node_id": int(node.id),
                    "error": error or "amneziawg_source_unavailable",
                }
            )

        if grouped.get("trusttunnel"):
            ok, epoch, rows, error = await _collect_trusttunnel(conn)
            results.append(
                {
                    "ok": True,
                    **_apply_trusttunnel(
                        db,
                        node=node,
                        devices=grouped["trusttunnel"],
                        epoch=epoch,
                        rows=rows,
                    ),
                }
                if ok
                else {
                    "ok": False,
                    "collector": "trusttunnel",
                    "node_id": int(node.id),
                    "error": error or "trusttunnel_source_unavailable",
                }
            )

        if grouped.get("mieru"):
            ok, rows, error = await _collect_mieru(conn)
            results.append(
                {
                    "ok": True,
                    **_apply_mieru_presence(
                        db,
                        node=node,
                        devices=grouped["mieru"],
                        rows=rows,
                    ),
                }
                if ok
                else {
                    "ok": False,
                    "collector": "mieru",
                    "node_id": int(node.id),
                    "error": error or "mieru_source_unavailable",
                }
            )

        if grouped.get("sudoku"):
            ok, ports, error = await _collect_established_tcp_ports(conn)
            results.append(
                {
                    "ok": True,
                    **_apply_sudoku_presence(
                        db,
                        node=node,
                        devices=grouped["sudoku"],
                        established_ports=ports,
                    ),
                }
                if ok
                else {
                    "ok": False,
                    "collector": "sudoku",
                    "node_id": int(node.id),
                    "error": error or "sudoku_source_unavailable",
                }
            )

        return results
    finally:
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:
                pass


async def reconcile_modern_quota_once() -> dict[str, Any]:
    db = SessionLocal()
    results: list[dict[str, Any]] = []
    try:
        nodes = (
            db.query(Node)
            .filter(
                Node.retired_at.is_(None),
                or_(
                    Node.node_type == NodeType.EXIT,
                    Node.agent_url == "local://core",
                ),
            )
            .order_by(Node.id.asc())
            .all()
        )

        for node in nodes:
            try:
                node_results = await _reconcile_node(db, node)
                db.commit()
                results.extend(node_results)
            except HTTPException as exc:
                db.rollback()
                results.append(
                    {
                        "ok": False,
                        "collector": "modern-runtime",
                        "node_id": int(node.id),
                        "error": f"http_{exc.status_code}:{str(exc.detail)[:500]}",
                    }
                )
            except Exception as exc:
                db.rollback()
                results.append(
                    {
                        "ok": False,
                        "collector": "modern-runtime",
                        "node_id": int(node.id),
                        "error": f"{type(exc).__name__}:{str(exc)[:500]}",
                    }
                )

        return {
            "ok": all(bool(item.get("ok")) for item in results) if results else True,
            "collectors": results,
        }
    finally:
        db.close()


async def modern_quota_runtime_loop() -> None:
    """Controller-owned reconcile loop with a process-wide failover lock.

    Current production runs one Uvicorn worker, but the flock also prevents
    duplicate collectors if API workers are increased later. A standby worker
    retries lock acquisition and can take over after the owner exits.
    """

    MODERN_ACCOUNTING_LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = MODERN_ACCOUNTING_LOCK.open("a+")
    owns_lock = False
    try:
        while True:
            if not owns_lock:
                try:
                    fcntl.flock(
                        lock_handle.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                    owns_lock = True
                except BlockingIOError:
                    await asyncio.sleep(MODERN_ACCOUNTING_INTERVAL_SECONDS)
                    continue

            started = time.monotonic()
            try:
                result = await reconcile_modern_quota_once()
                if not bool(result.get("ok")):
                    print(
                        json.dumps(
                            {
                                "event": "modern_quota_reconcile",
                                **result,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        flush=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    json.dumps(
                        {
                            "event": "modern_quota_reconcile_crash",
                            "ok": False,
                            "error": f"{type(exc).__name__}:{str(exc)[:800]}",
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    flush=True,
                )

            delay = max(
                MODERN_ACCOUNTING_INTERVAL_SECONDS
                - (time.monotonic() - started),
                0.25,
            )
            await asyncio.sleep(delay)
    finally:
        if owns_lock:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        lock_handle.close()


def capability_payload() -> dict[str, dict[str, bool]]:
    protocols = {
        "wireguard",
        "amneziawg",
        "trusttunnel",
        "mieru",
        "sudoku",
        "hysteria2",
        "tuic",
        "anytls",
        "naive",
        "shadowtls",
        "snell",
    }
    return {
        protocol: {
            "presence": protocol in PRESENCE_ACCOUNTING_PROTOCOLS,
            "traffic": protocol in TRAFFIC_ACCOUNTING_PROTOCOLS,
        }
        for protocol in sorted(protocols)
    }


__all__ = [
    "MODERN_ACCOUNTING_INTERVAL_SECONDS",
    "PRESENCE_ACCOUNTING_PROTOCOLS",
    "TRAFFIC_ACCOUNTING_PROTOCOLS",
    "capability_payload",
    "modern_quota_runtime_loop",
    "reconcile_modern_quota_once",
]
