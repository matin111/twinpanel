from __future__ import annotations

import asyncio
import base64
import fcntl
import json
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_

from ..database import SessionLocal
from ..models import Node, NodeType
from ..modern_protocol_runtime import CONFIG_PATH, SERVICE_NAME, STATE_PATH
from ..modern_protocol_runtime_v2 import TAGS
from ..node_runtime_connection import connect_protocol_runtime
from ..quota_models import QuotaCursor
from . import modern_quota_runtime_v257 as canonical
from .quota_node_sync import build_node_devices


SINGBOX_ACCOUNTING_PROTOCOLS = frozenset(
    {"hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell"}
)
SINGBOX_ACCOUNTING_INTERVAL_SECONDS = 5.0
SINGBOX_ACCOUNTING_LOCK = Path("/run/twinpanel-singbox-quota-v265.lock")
SINGBOX_API_TAG = "twinpanel-accounting-api"
SINGBOX_API_LISTEN = "127.0.0.1"
SINGBOX_API_PORT = 19092
SINGBOX_CLOSED_RETENTION_LIMIT = 1000


def activate_singbox_capabilities() -> None:
    """Expose only capabilities backed by the native collector.

    public_connection_live_v4 imports canonical.capability_payload as a function;
    that function resolves these module globals at call time. Updating the two
    immutable sets during application startup therefore keeps the public route
    DB-only while accurately advertising the newly installed collector.
    """

    canonical.PRESENCE_ACCOUNTING_PROTOCOLS = frozenset(
        set(canonical.PRESENCE_ACCOUNTING_PROTOCOLS) | set(SINGBOX_ACCOUNTING_PROTOCOLS)
    )
    canonical.TRAFFIC_ACCOUNTING_PROTOCOLS = frozenset(
        set(canonical.TRAFFIC_ACCOUNTING_PROTOCOLS) | set(SINGBOX_ACCOUNTING_PROTOCOLS)
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


async def _run_node_command(
    conn,
    script: str,
    *,
    timeout: float,
) -> tuple[bool, str]:
    try:
        result = await conn.run(
            "bash -lc " + shlex.quote(script),
            check=False,
            timeout=timeout,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}:{exc}"

    stdout = str(getattr(result, "stdout", "") or "")
    stderr = str(getattr(result, "stderr", "") or "")
    output = stdout + (("\n" + stderr) if stderr else "")
    return int(getattr(result, "exit_status", 1)) == 0, output.strip()


def _api_mutation_script() -> str:
    """Return an idempotent node-local config mutation.

    The API is loopback-only and authenticated.  The secret is node runtime
    state, never a subscriber credential. Existing top-level sing-box config is
    preserved and only TwinPanel's tagged API service is owned here.
    """

    return f'''from __future__ import annotations
import json
import os
import secrets

CONFIG = {CONFIG_PATH!r}
STATE = {STATE_PATH!r}
TAG = {SINGBOX_API_TAG!r}
LISTEN = {SINGBOX_API_LISTEN!r}
PORT = {SINGBOX_API_PORT!r}


def load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value
    except FileNotFoundError:
        return default


with open(CONFIG, "r", encoding="utf-8") as handle:
    doc = json.load(handle)
if not isinstance(doc, dict):
    raise SystemExit("sing-box config is not an object")

state = load(STATE, {{}})
if not isinstance(state, dict):
    state = {{}}

services = doc.get("services")
if not isinstance(services, list):
    services = []

existing = next(
    (
        item for item in services
        if isinstance(item, dict) and item.get("tag") == TAG
    ),
    None,
)

api_state = state.get("accounting_api")
if not isinstance(api_state, dict):
    api_state = {{}}

secret = str(api_state.get("secret") or "").strip()
if not secret and isinstance(existing, dict):
    secret = str(existing.get("secret") or "").strip()
if not secret:
    secret = secrets.token_urlsafe(48)

desired = {{
    "type": "api",
    "tag": TAG,
    "listen": LISTEN,
    "listen_port": PORT,
    "secret": secret,
}}

config_changed = existing != desired
if isinstance(existing, dict):
    if config_changed:
        existing.clear()
        existing.update(desired)
else:
    services.append(desired)
    config_changed = True

doc["services"] = services

new_api_state = {{
    "tag": TAG,
    "listen": LISTEN,
    "port": PORT,
    "secret": secret,
}}
state_changed = api_state != new_api_state
state["accounting_api"] = new_api_state

if config_changed:
    with open(CONFIG + ".accounting-api-new", "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=2)
        handle.write("\\n")
    os.chmod(CONFIG + ".accounting-api-new", 0o600)

if config_changed or state_changed:
    with open(STATE + ".accounting-api-new", "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\\n")
    os.chmod(STATE + ".accounting-api-new", 0o600)

print("CONFIG_CHANGED=" + ("1" if config_changed else "0"))
print("STATE_CHANGED=" + ("1" if state_changed else "0"))
'''


async def ensure_singbox_accounting_api(conn) -> tuple[bool, bool, str | None]:
    encoded = base64.b64encode(_api_mutation_script().encode("utf-8")).decode("ascii")
    script = f'''set -eu
command -v /usr/local/bin/twinpanel-sing-box >/dev/null
test -s {shlex.quote(CONFIG_PATH)}
result="$(printf '%s' {shlex.quote(encoded)} | base64 -d | python3)"
printf '%s\\n' "$result"
config_changed=0
state_changed=0
printf '%s\\n' "$result" | grep -q '^CONFIG_CHANGED=1$' && config_changed=1 || true
printf '%s\\n' "$result" | grep -q '^STATE_CHANGED=1$' && state_changed=1 || true

if [ "$config_changed" = 1 ]; then
  /usr/local/bin/twinpanel-sing-box check -c {shlex.quote(CONFIG_PATH + '.accounting-api-new')}
  stamp="$(date +%Y%m%d-%H%M%S)"
  cfg_backup={shlex.quote(CONFIG_PATH)}.bak-accounting-api-$stamp
  state_backup={shlex.quote(STATE_PATH)}.bak-accounting-api-$stamp
  cp -a {shlex.quote(CONFIG_PATH)} "$cfg_backup"
  had_state=0
  if [ -s {shlex.quote(STATE_PATH)} ]; then
    cp -a {shlex.quote(STATE_PATH)} "$state_backup"
    had_state=1
  fi
  mv {shlex.quote(CONFIG_PATH + '.accounting-api-new')} {shlex.quote(CONFIG_PATH)}
  if [ -s {shlex.quote(STATE_PATH + '.accounting-api-new')} ]; then
    mv {shlex.quote(STATE_PATH + '.accounting-api-new')} {shlex.quote(STATE_PATH)}
  fi
  chmod 600 {shlex.quote(CONFIG_PATH)} {shlex.quote(STATE_PATH)}
  if ! systemctl restart {shlex.quote(SERVICE_NAME)}.service; then
    cp -a "$cfg_backup" {shlex.quote(CONFIG_PATH)}
    if [ "$had_state" = 1 ]; then
      cp -a "$state_backup" {shlex.quote(STATE_PATH)}
    else
      rm -f {shlex.quote(STATE_PATH)}
    fi
    systemctl restart {shlex.quote(SERVICE_NAME)}.service || true
    exit 51
  fi
elif [ "$state_changed" = 1 ]; then
  mv {shlex.quote(STATE_PATH + '.accounting-api-new')} {shlex.quote(STATE_PATH)}
  chmod 600 {shlex.quote(STATE_PATH)}
fi

systemctl is-active --quiet {shlex.quote(SERVICE_NAME)}.service
'''
    ok, output = await _run_node_command(conn, script, timeout=30)
    if not ok:
        return False, False, output[-900:] or "singbox_accounting_api_setup_failed"
    changed = "CONFIG_CHANGED=1" in output
    return True, changed, None


def _snapshot_script() -> str:
    """Node-local exact protobuf reader for the first gRPC-Web snapshot.

    No human-formatted CLI byte output is used. The script reads exact int64
    fields from daemon.Connection and exits immediately after the initial reset
    snapshot (active plus retained closed connections).
    """

    return f'''from __future__ import annotations
import http.client
import json
import struct
import subprocess
import time

STATE = {STATE_PATH!r}
HOST = {SINGBOX_API_LISTEN!r}
PORT = {SINGBOX_API_PORT!r}
SERVICE = {SERVICE_NAME!r}
MAX_FRAME = 32 * 1024 * 1024


def read_varint(data, offset):
    value = 0
    shift = 0
    while True:
        if offset >= len(data) or shift >= 70:
            raise ValueError("invalid protobuf varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7f) << shift
        if not (byte & 0x80):
            return value, offset
        shift += 7


def fields(data):
    offset = 0
    while offset < len(data):
        key, offset = read_varint(data, offset)
        number = key >> 3
        wire = key & 7
        if number <= 0:
            raise ValueError("invalid protobuf field")
        if wire == 0:
            value, offset = read_varint(data, offset)
        elif wire == 1:
            if offset + 8 > len(data):
                raise ValueError("truncated fixed64")
            value = data[offset:offset + 8]
            offset += 8
        elif wire == 2:
            size, offset = read_varint(data, offset)
            if size < 0 or offset + size > len(data):
                raise ValueError("truncated bytes")
            value = data[offset:offset + size]
            offset += size
        elif wire == 5:
            if offset + 4 > len(data):
                raise ValueError("truncated fixed32")
            value = data[offset:offset + 4]
            offset += 4
        else:
            raise ValueError("unsupported protobuf wire type")
        yield number, wire, value


def text(value):
    return bytes(value).decode("utf-8", errors="strict")


def parse_connection(data):
    row = {{
        "id": "",
        "inbound": "",
        "inbound_type": "",
        "source": "",
        "user": "",
        "created_at_ms": 0,
        "closed_at_ms": 0,
        "uplink_total": 0,
        "downlink_total": 0,
    }}
    for number, wire, value in fields(data):
        if wire == 2 and number == 1:
            row["id"] = text(value)
        elif wire == 2 and number == 2:
            row["inbound"] = text(value)
        elif wire == 2 and number == 3:
            row["inbound_type"] = text(value)
        elif wire == 2 and number == 6:
            row["source"] = text(value)
        elif wire == 2 and number == 10:
            row["user"] = text(value)
        elif wire == 0 and number == 12:
            row["created_at_ms"] = int(value)
        elif wire == 0 and number == 13:
            row["closed_at_ms"] = int(value)
        elif wire == 0 and number == 16:
            row["uplink_total"] = int(value)
        elif wire == 0 and number == 17:
            row["downlink_total"] = int(value)
    return row


def parse_event(data):
    event_id = ""
    connection = None
    for number, wire, value in fields(data):
        if wire == 2 and number == 2:
            event_id = text(value)
        elif wire == 2 and number == 3:
            connection = parse_connection(value)
    if connection is None:
        return None
    if not connection["id"]:
        connection["id"] = event_id
    return connection


def parse_events(data):
    rows = []
    reset = False
    for number, wire, value in fields(data):
        if wire == 2 and number == 1:
            row = parse_event(value)
            if row is not None:
                rows.append(row)
        elif wire == 0 and number == 2:
            reset = bool(value)
    return reset, rows


def runtime_epoch():
    try:
        value = subprocess.check_output(
            ["systemctl", "show", SERVICE + ".service", "-p", "ActiveEnterTimestampMonotonic", "--value"],
            text=True,
            timeout=2,
        ).strip()
    except Exception:
        value = ""
    if value and value != "0":
        return "systemd-" + value
    try:
        pid = subprocess.check_output(
            ["systemctl", "show", SERVICE + ".service", "-p", "MainPID", "--value"],
            text=True,
            timeout=2,
        ).strip()
        if pid and pid != "0":
            with open("/proc/" + pid + "/stat", "r", encoding="utf-8") as handle:
                parts = handle.read().split()
            if len(parts) > 21:
                return "proc-" + parts[21]
    except Exception:
        pass
    raise RuntimeError("sing-box runtime epoch unavailable")


with open(STATE, "r", encoding="utf-8") as handle:
    state = json.load(handle)
api_state = state.get("accounting_api") if isinstance(state, dict) else None
if not isinstance(api_state, dict):
    raise SystemExit("accounting API state missing")
secret = str(api_state.get("secret") or "").strip()
if not secret:
    raise SystemExit("accounting API secret missing")

body = b"\\x00" + struct.pack(">I", 0)
connection = http.client.HTTPConnection(HOST, PORT, timeout=5)
connection.request(
    "POST",
    "/daemon.StartedService/SubscribeConnections",
    body=body,
    headers={{
        "Content-Type": "application/grpc-web+proto",
        "Accept": "application/grpc-web+proto",
        "X-Grpc-Web": "1",
        "TE": "trailers",
        "Authorization": "Bearer " + secret,
    }},
)
response = connection.getresponse()
if response.status != 200:
    raise RuntimeError("sing-box API HTTP status " + str(response.status))
header = response.read(5)
if len(header) != 5:
    raise RuntimeError("sing-box API initial frame missing")
flags = header[0]
size = struct.unpack(">I", header[1:])[0]
if flags & 0x80:
    raise RuntimeError("sing-box API returned trailers before snapshot")
if flags & 0x01:
    raise RuntimeError("compressed sing-box API frame unsupported")
if size > MAX_FRAME:
    raise RuntimeError("sing-box API frame too large")
payload = response.read(size)
if len(payload) != size:
    raise RuntimeError("truncated sing-box API frame")
connection.close()
reset, rows = parse_events(payload)
if not reset:
    raise RuntimeError("sing-box API initial snapshot missing reset marker")

print(json.dumps({{
    "epoch": runtime_epoch(),
    "snapshot_ms": int(time.time() * 1000),
    "reset": True,
    "rows": rows,
}}, separators=(",", ":")))
'''


async def collect_singbox_snapshot(
    conn,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    encoded = base64.b64encode(_snapshot_script().encode("utf-8")).decode("ascii")
    ok, output = await _run_node_command(
        conn,
        f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3",
        timeout=10,
    )
    if not ok:
        return False, None, output[-1200:] or "singbox_snapshot_failed"

    line = next((item.strip() for item in reversed(output.splitlines()) if item.strip()), "")
    try:
        payload = json.loads(line)
    except Exception as exc:
        return False, None, f"singbox_snapshot_json_failed:{exc}:{line[-600:]}"

    if not isinstance(payload, dict) or payload.get("reset") is not True:
        return False, None, "singbox_snapshot_not_authoritative"
    epoch = str(payload.get("epoch") or "").strip()
    rows = payload.get("rows")
    snapshot_ms = _safe_int(payload.get("snapshot_ms"))
    if not epoch or not isinstance(rows, list) or snapshot_ms <= 0:
        return False, None, "singbox_snapshot_contract_invalid"

    normalized: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        row = {
            "id": str(raw.get("id") or "").strip(),
            "inbound": str(raw.get("inbound") or "").strip(),
            "inbound_type": str(raw.get("inbound_type") or "").strip().lower(),
            "source": str(raw.get("source") or "").strip(),
            "user": str(raw.get("user") or "").strip(),
            "created_at_ms": _safe_int(raw.get("created_at_ms")),
            "closed_at_ms": _safe_int(raw.get("closed_at_ms")),
            "uplink_total": _safe_int(raw.get("uplink_total")),
            "downlink_total": _safe_int(raw.get("downlink_total")),
        }
        if not row["id"]:
            continue
        normalized.append(row)

    return True, {
        "epoch": epoch,
        "snapshot_ms": snapshot_ms,
        "rows": normalized,
    }, None


def _source_ip(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")][:64] or None
    if text.count(":") == 1:
        return text.rsplit(":", 1)[0][:64] or None
    if ":" in text:
        # Unbracketed IPv6 sources are retained without guessing a port split.
        return text[:64]
    return text[:64]


def _connection_source_key(protocol: str, connection_id: str) -> str:
    return f"singbox:{protocol}:{connection_id}"[:220]


def _watermark_source_key(protocol: str, identity: str) -> str:
    return f"singbox-watermark:{protocol}:{identity}"[:220]


def _cursor_for_source(db, *, node_id: int, source_key: str) -> QuotaCursor | None:
    return (
        db.query(QuotaCursor)
        .filter(
            QuotaCursor.node_id == int(node_id),
            QuotaCursor.source_key == str(source_key),
        )
        .first()
    )


def _assert_cursor_identity(
    cursor: QuotaCursor,
    *,
    device: dict[str, Any],
    protocol: str,
) -> None:
    if (
        int(cursor.subscription_id) != int(device["subscription_id"])
        or int(cursor.device_id) != int(device["device_id"])
        or str(cursor.protocol) != protocol
    ):
        raise RuntimeError("singbox_cursor_identity_conflict")


def _set_connection_baseline(
    db,
    *,
    node_id: int,
    device: dict[str, Any],
    protocol: str,
    source_key: str,
    epoch: str,
    uplink: int,
    downlink: int,
    snapshot_ms: int,
    observed_at: datetime,
) -> QuotaCursor:
    cursor = _cursor_for_source(db, node_id=node_id, source_key=source_key)
    if cursor is None:
        cursor = QuotaCursor(
            node_id=int(node_id),
            subscription_id=int(device["subscription_id"]),
            device_id=int(device["device_id"]),
            protocol=protocol,
            source_key=source_key,
            counter_mode="cumulative",
            counter_epoch=canonical._short_epoch(epoch, fallback=f"singbox:{node_id}"),
            last_sequence=max(int(snapshot_ms), 1),
            last_uplink_value=max(int(uplink), 0),
            last_downlink_value=max(int(downlink), 0),
            updated_at=canonical._naive(observed_at),
        )
        db.add(cursor)
    else:
        _assert_cursor_identity(cursor, device=device, protocol=protocol)
        cursor.counter_mode = "cumulative"
        cursor.counter_epoch = canonical._short_epoch(epoch, fallback=f"singbox:{node_id}")
        cursor.last_sequence = max(int(snapshot_ms), 1)
        cursor.last_uplink_value = max(int(uplink), 0)
        cursor.last_downlink_value = max(int(downlink), 0)
        cursor.updated_at = canonical._naive(observed_at)
    db.flush()
    return cursor


def _observation_mode(
    *,
    cursor: QuotaCursor | None,
    epoch: str,
    watermark_epoch: str | None,
    previous_snapshot_ms: int | None,
    created_at_ms: int,
) -> str:
    """Return baseline, delta or full for one exact connection observation."""

    normalized_epoch = canonical._short_epoch(epoch, fallback="singbox")
    if watermark_epoch != normalized_epoch:
        return "baseline"
    if cursor is not None:
        if str(cursor.counter_epoch) == normalized_epoch:
            return "delta"
        return "baseline"
    if previous_snapshot_ms is not None and int(created_at_ms) > int(previous_snapshot_ms):
        return "full"
    return "baseline"


def _watermark(
    db,
    *,
    node_id: int,
    device: dict[str, Any],
    protocol: str,
    identity: str,
) -> QuotaCursor | None:
    return _cursor_for_source(
        db,
        node_id=node_id,
        source_key=_watermark_source_key(protocol, identity),
    )


def _advance_watermark(
    db,
    *,
    node_id: int,
    device: dict[str, Any],
    protocol: str,
    identity: str,
    epoch: str,
    snapshot_ms: int,
    observed_at: datetime,
) -> None:
    source_key = _watermark_source_key(protocol, identity)
    cursor = _cursor_for_source(db, node_id=node_id, source_key=source_key)
    normalized_epoch = canonical._short_epoch(epoch, fallback=f"singbox:{node_id}")
    if cursor is None:
        db.add(
            QuotaCursor(
                node_id=int(node_id),
                subscription_id=int(device["subscription_id"]),
                device_id=int(device["device_id"]),
                protocol=protocol,
                source_key=source_key,
                counter_mode="snapshot",
                counter_epoch=normalized_epoch,
                last_sequence=max(int(snapshot_ms), 1),
                last_uplink_value=0,
                last_downlink_value=0,
                updated_at=canonical._naive(observed_at),
            )
        )
    else:
        _assert_cursor_identity(cursor, device=device, protocol=protocol)
        cursor.counter_mode = "snapshot"
        cursor.counter_epoch = normalized_epoch
        cursor.last_sequence = max(int(snapshot_ms), int(cursor.last_sequence or 0))
        cursor.last_uplink_value = 0
        cursor.last_downlink_value = 0
        cursor.updated_at = canonical._naive(observed_at)
    db.flush()


def _prune_missing_connection_cursors(
    db,
    *,
    node_id: int,
    device: dict[str, Any],
    protocol: str,
    current_source_keys: set[str],
) -> int:
    prefix = f"singbox:{protocol}:"
    rows = (
        db.query(QuotaCursor)
        .filter(
            QuotaCursor.node_id == int(node_id),
            QuotaCursor.device_id == int(device["device_id"]),
            QuotaCursor.protocol == protocol,
            QuotaCursor.source_key.like(prefix + "%"),
        )
        .all()
    )
    removed = 0
    for cursor in rows:
        if str(cursor.source_key) in current_source_keys:
            continue
        db.delete(cursor)
        removed += 1
    return removed


def apply_singbox_snapshot(
    db,
    *,
    node: Node,
    protocol: str,
    devices: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    protocol = str(protocol or "").strip().lower()
    if protocol not in SINGBOX_ACCOUNTING_PROTOCOLS:
        raise ValueError(f"unsupported sing-box accounting protocol: {protocol}")

    epoch = str(snapshot.get("epoch") or "").strip()
    snapshot_ms = _safe_int(snapshot.get("snapshot_ms"))
    rows = snapshot.get("rows")
    if not epoch or snapshot_ms <= 0 or not isinstance(rows, list):
        raise RuntimeError("singbox_snapshot_contract_invalid")

    observed_at = _utcnow()
    expected_tag = str(TAGS.get(protocol) or "").strip()
    if not expected_tag:
        raise RuntimeError("singbox_protocol_tag_missing")

    protocol_rows = [
        row for row in rows
        if isinstance(row, dict)
        and str(row.get("inbound") or "").strip() == expected_tag
        and str(row.get("inbound_type") or "").strip().lower() == protocol
        and str(row.get("user") or "").strip()
    ]
    closed_retained = sum(1 for row in rows if _safe_int(row.get("closed_at_ms")) > 0)
    retention_saturated = closed_retained >= SINGBOX_CLOSED_RETENTION_LIMIT

    opened = closed = online_count = matched_connections = 0
    baselined = usage_events = accepted_bytes = full_charged = pruned = 0

    for device in devices:
        identity = str(
            device.get("telemetry_identity") or device.get("identity") or ""
        ).strip()
        if not identity:
            raise RuntimeError("singbox_device_identity_missing")

        matching = [row for row in protocol_rows if str(row.get("user") or "") == identity]
        active_rows = [row for row in matching if _safe_int(row.get("closed_at_ms")) == 0]
        online = bool(active_rows)
        client_ip = _source_ip((active_rows or matching or [{{}}])[0].get("source"))

        presence = canonical._mark_presence(
            db,
            node_id=int(node.id),
            device=device,
            protocol=protocol,
            online=online,
            observed_at=observed_at,
            client_ip=client_ip,
            evidence=f"singbox:{identity}:active={len(active_rows)}",
        )
        opened += int(presence.get("opened") or 0)
        closed += int(presence.get("closed") or 0)
        online_count += int(online)
        matched_connections += len(matching)

        active_sessions = canonical._active_sessions(
            db,
            node_id=int(node.id),
            device_id=int(device["device_id"]),
            protocol=protocol,
        )
        session_key = active_sessions[0].session_key if active_sessions else None

        watermark = _watermark(
            db,
            node_id=int(node.id),
            device=device,
            protocol=protocol,
            identity=identity,
        )
        normalized_epoch = canonical._short_epoch(epoch, fallback=f"singbox:{int(node.id)}")
        watermark_epoch = str(watermark.counter_epoch) if watermark is not None else None
        previous_snapshot_ms = (
            int(watermark.last_sequence)
            if watermark is not None and watermark_epoch == normalized_epoch
            else None
        )

        current_source_keys: set[str] = set()
        for row in matching:
            connection_id = str(row.get("id") or "").strip()
            if not connection_id:
                raise RuntimeError("singbox_connection_id_missing")
            created_at_ms = _safe_int(row.get("created_at_ms"))
            if created_at_ms <= 0 or created_at_ms > snapshot_ms + 5000:
                raise RuntimeError("singbox_connection_timestamp_invalid")
            uplink = _safe_int(row.get("uplink_total"))
            downlink = _safe_int(row.get("downlink_total"))
            source_key = _connection_source_key(protocol, connection_id)
            current_source_keys.add(source_key)
            cursor = _cursor_for_source(
                db,
                node_id=int(node.id),
                source_key=source_key,
            )
            if cursor is not None:
                _assert_cursor_identity(cursor, device=device, protocol=protocol)

            mode = _observation_mode(
                cursor=cursor,
                epoch=epoch,
                watermark_epoch=watermark_epoch,
                previous_snapshot_ms=previous_snapshot_ms,
                created_at_ms=created_at_ms,
            )

            if mode == "baseline":
                _set_connection_baseline(
                    db,
                    node_id=int(node.id),
                    device=device,
                    protocol=protocol,
                    source_key=source_key,
                    epoch=epoch,
                    uplink=uplink,
                    downlink=downlink,
                    snapshot_ms=snapshot_ms,
                    observed_at=observed_at,
                )
                baselined += 1
                continue

            if mode == "full":
                _set_connection_baseline(
                    db,
                    node_id=int(node.id),
                    device=device,
                    protocol=protocol,
                    source_key=source_key,
                    epoch=epoch,
                    uplink=0,
                    downlink=0,
                    snapshot_ms=max(previous_snapshot_ms or 1, 1),
                    observed_at=observed_at,
                )
                full_charged += 1

            usage = canonical._baseline_or_apply_cumulative(
                db,
                node_id=int(node.id),
                device=device,
                protocol=protocol,
                source_key=source_key,
                counter_epoch=epoch,
                uplink=uplink,
                downlink=downlink,
                session_key=session_key,
                client_ip=_source_ip(row.get("source")),
                reported_at=observed_at,
            )
            baselined += int(bool(usage.get("baselined")))
            usage_events += int(bool(usage.get("event")))
            accepted_bytes += int(usage.get("accepted_bytes") or 0)

        _advance_watermark(
            db,
            node_id=int(node.id),
            device=device,
            protocol=protocol,
            identity=identity,
            epoch=epoch,
            snapshot_ms=snapshot_ms,
            observed_at=observed_at,
        )
        pruned += _prune_missing_connection_cursors(
            db,
            node_id=int(node.id),
            device=device,
            protocol=protocol,
            current_source_keys=current_source_keys,
        )

    return {
        "collector": f"singbox-{protocol}",
        "node_id": int(node.id),
        "targets": len(devices),
        "matched_connections": matched_connections,
        "online": online_count,
        "opened": opened,
        "closed": closed,
        "baselined": baselined,
        "full_charged_connections": full_charged,
        "usage_events": usage_events,
        "accepted_bytes": accepted_bytes,
        "pruned_cursors": pruned,
        "closed_retained": closed_retained,
        "retention_saturated": retention_saturated,
    }


def _devices_by_protocol(db, node_id: int) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in build_node_devices(db, int(node_id)):
        protocol = str(item.get("protocol") or "").strip().lower()
        if protocol not in SINGBOX_ACCOUNTING_PROTOCOLS:
            continue
        grouped.setdefault(protocol, []).append(dict(item))
    return grouped


async def reconcile_singbox_quota_once() -> dict[str, Any]:
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
            grouped = _devices_by_protocol(db, int(node.id))
            if not grouped:
                continue

            conn = None
            try:
                conn = await connect_protocol_runtime(node, db)
                api_ok, api_changed, api_error = await ensure_singbox_accounting_api(conn)
                if not api_ok:
                    db.commit()
                    results.append({
                        "ok": False,
                        "collector": "singbox-native",
                        "node_id": int(node.id),
                        "error": api_error or "singbox_accounting_api_unavailable",
                    })
                    continue

                snapshot_ok, snapshot, snapshot_error = await collect_singbox_snapshot(conn)
                if not snapshot_ok or snapshot is None:
                    db.commit()
                    results.append({
                        "ok": False,
                        "collector": "singbox-native",
                        "node_id": int(node.id),
                        "api_changed": api_changed,
                        "error": snapshot_error or "singbox_snapshot_unavailable",
                    })
                    continue

                for protocol in sorted(grouped):
                    try:
                        applied = apply_singbox_snapshot(
                            db,
                            node=node,
                            protocol=protocol,
                            devices=grouped[protocol],
                            snapshot=snapshot,
                        )
                        db.commit()
                        results.append({
                            "ok": not bool(applied.get("retention_saturated")),
                            "api_changed": api_changed,
                            **applied,
                            **(
                                {"error": "singbox_closed_retention_saturated"}
                                if applied.get("retention_saturated")
                                else {}
                            ),
                        })
                    except HTTPException as exc:
                        db.rollback()
                        results.append({
                            "ok": False,
                            "collector": f"singbox-{protocol}",
                            "node_id": int(node.id),
                            "error": f"http_{exc.status_code}:{str(exc.detail)[:500]}",
                        })
                    except Exception as exc:
                        db.rollback()
                        results.append({
                            "ok": False,
                            "collector": f"singbox-{protocol}",
                            "node_id": int(node.id),
                            "error": f"{type(exc).__name__}:{str(exc)[:500]}",
                        })

            except HTTPException as exc:
                db.rollback()
                results.append({
                    "ok": False,
                    "collector": "singbox-native",
                    "node_id": int(node.id),
                    "error": f"http_{exc.status_code}:{str(exc.detail)[:500]}",
                })
            except Exception as exc:
                db.rollback()
                results.append({
                    "ok": False,
                    "collector": "singbox-native",
                    "node_id": int(node.id),
                    "error": f"{type(exc).__name__}:{str(exc)[:500]}",
                })
            finally:
                if conn is not None:
                    conn.close()
                    try:
                        await conn.wait_closed()
                    except Exception:
                        pass

        return {
            "ok": all(bool(item.get("ok")) for item in results) if results else True,
            "collectors": results,
        }
    finally:
        db.close()


async def singbox_native_accounting_loop() -> None:
    SINGBOX_ACCOUNTING_LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = SINGBOX_ACCOUNTING_LOCK.open("a+")
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
                    await asyncio.sleep(SINGBOX_ACCOUNTING_INTERVAL_SECONDS)
                    continue

            started = time.monotonic()
            try:
                result = await reconcile_singbox_quota_once()
                if not bool(result.get("ok")):
                    print(
                        json.dumps(
                            {"event": "singbox_native_accounting_reconcile", **result},
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
                            "event": "singbox_native_accounting_crash",
                            "ok": False,
                            "error": f"{type(exc).__name__}:{str(exc)[:800]}",
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    flush=True,
                )

            delay = max(
                SINGBOX_ACCOUNTING_INTERVAL_SECONDS - (time.monotonic() - started),
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


__all__ = [
    "SINGBOX_ACCOUNTING_PROTOCOLS",
    "activate_singbox_capabilities",
    "apply_singbox_snapshot",
    "collect_singbox_snapshot",
    "ensure_singbox_accounting_api",
    "reconcile_singbox_quota_once",
    "singbox_native_accounting_loop",
]
