from __future__ import annotations

import asyncio
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_

from ..database import SessionLocal
from ..models import Node
from ..quota_models import QuotaSession
from ..quota_schemas import SessionCloseIn, SessionOpenIn, UsageEventIn
from ..quota_service import close_session
from ..routers.provision import ssh_connect_saved
from .quota_node_sync import build_node_devices
from .reseller_traffic_pool import apply_usage_event, open_session


# Session truth comes from the VPN daemon, not from page views or account
# delivery.  This keeps first-use activation tied to a real authenticated VPN
# session and makes the public Connect page reflect the same canonical quota
# ledger used for enforcement.
QUOTA_RUNTIME_INTERVAL_SECONDS = 5.0


def _local_occtl_json() -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["occtl", "--json", "show", "users"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)

    return proc.returncode == 0, str(proc.stdout or "")


async def _remote_occtl_json(node: Node, db) -> tuple[bool, str]:
    conn = None
    try:
        conn = await ssh_connect_saved(node, db)
        result = await conn.run(
            "occtl --json show users",
            check=False,
            timeout=8,
        )
        output = (
            str(result.stdout or "")
            + ("\n" + str(result.stderr or "") if result.stderr else "")
        ).strip()
        return int(result.exit_status) == 0, output
    except Exception as exc:
        return False, str(exc)
    finally:
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:
                pass


def _candidate_rows(value):
    if isinstance(value, list):
        for item in value:
            yield from _candidate_rows(item)
        return

    if not isinstance(value, dict):
        return

    keys = {str(key).strip().lower() for key in value.keys()}
    if "username" in keys and ("id" in keys or "device" in keys):
        yield value
        return

    for item in value.values():
        if isinstance(item, (dict, list)):
            yield from _candidate_rows(item)


def _value(row: dict, *names, default=None):
    lookup = {
        str(key).strip().lower(): value
        for key, value in row.items()
    }
    for name in names:
        key = str(name).strip().lower()
        if key in lookup:
            return lookup[key]
    return default


def _int_counter(value) -> int:
    if isinstance(value, bool) or value is None:
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

    # Defensive compatibility for human-readable outputs, although occtl JSON
    # normally exposes RX/TX as raw decimal byte strings.
    parts = text.split()
    if not parts:
        return 0
    try:
        number = float(parts[0])
    except ValueError:
        return 0

    unit = (parts[1] if len(parts) > 1 else "B").upper()
    factor = {
        "B": 1,
        "KB": 1000,
        "KIB": 1024,
        "MB": 1000**2,
        "MIB": 1024**2,
        "GB": 1000**3,
        "GIB": 1024**3,
        "TB": 1000**4,
        "TIB": 1024**4,
    }.get(unit, 1)
    return max(int(number * factor), 0)


def _parse_occtl_users(raw: str) -> list[dict]:
    try:
        payload = json.loads(raw)
    except Exception:
        return []

    sessions: list[dict] = []

    for row in _candidate_rows(payload):
        username = str(_value(row, "Username", default="") or "").strip()
        if not username:
            continue

        session_id = str(_value(row, "ID", default="") or "").strip()
        connected_at = str(
            _value(row, "raw_connected_at", "Connected at", default="") or ""
        ).strip()
        client_ip = str(
            _value(row, "Remote IP", "remote_ip", "IP", default="") or ""
        ).strip()

        # ID is the daemon's active connection identifier. raw_connected_at
        # prevents a recycled ID after an ocserv restart from colliding with a
        # historical closed session.
        identity = session_id or str(_value(row, "Device", default="") or "").strip()
        if not identity:
            identity = client_ip or username

        session_key = "ocserv:{}:{}:{}".format(
            identity,
            connected_at or "current",
            username,
        )[:160]

        sessions.append(
            {
                "username": username,
                "session_key": session_key,
                "client_ip": client_ip or None,
                "rx": _int_counter(_value(row, "RX", "raw_rx", default=0)),
                "tx": _int_counter(_value(row, "TX", "raw_tx", default=0)),
            }
        )

    return sessions


async def _collect_node_users(node: Node, db) -> tuple[bool, list[dict], str | None]:
    if bool(getattr(node, "is_mother", False)):
        ok, output = await asyncio.to_thread(_local_occtl_json)
    else:
        ok, output = await _remote_occtl_json(node, db)

    if not ok:
        return False, [], output[-600:]

    try:
        parsed = _parse_occtl_users(output)
    except Exception as exc:
        return False, [], f"occtl_parse_failed:{exc}"

    return True, parsed, None


def _device_map(db, node_id: int) -> dict[str, dict]:
    devices = build_node_devices(db, int(node_id))
    return {
        str(item.get("identity") or ""): item
        for item in devices
        if str(item.get("protocol") or "") == "openconnect"
        and str(item.get("identity") or "")
    }


def _touch_session(db, node_id: int, session_key: str, now: datetime) -> None:
    row = (
        db.query(QuotaSession)
        .filter(
            QuotaSession.node_id == int(node_id),
            QuotaSession.session_key == session_key,
            QuotaSession.status == "active",
        )
        .first()
    )
    if row is not None:
        row.last_seen_at = now


def _apply_observed_sessions(db, node: Node, observed: list[dict]) -> dict:
    node_id = int(node.id)
    devices = _device_map(db, node_id)
    now_aware = datetime.now(timezone.utc)
    now_naive = now_aware.replace(tzinfo=None)
    sequence_base = int(time.time_ns() // 1_000_000)

    opened = 0
    usage_events = 0
    ignored = 0
    active_keys: set[str] = set()

    for index, session in enumerate(observed):
        device = devices.get(session["username"])
        if device is None:
            ignored += 1
            continue

        session_key = str(session["session_key"])
        active_keys.add(session_key)

        open_result = open_session(
            db,
            node_id,
            SessionOpenIn(
                session_key=session_key,
                subscription_id=int(device["subscription_id"]),
                device_id=int(device["device_id"]),
                protocol="openconnect",
                client_ip=session.get("client_ip"),
            ),
        )
        if not bool(open_result.get("duplicate")):
            opened += 1

        _touch_session(db, node_id, session_key, now_naive)

        rx = max(int(session.get("rx") or 0), 0)
        tx = max(int(session.get("tx") or 0), 0)
        sequence = sequence_base + index
        event_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"twinpanel:ocserv:{node_id}:{session_key}:{sequence}:{rx}:{tx}",
            )
        )

        apply_usage_event(
            db,
            node_id,
            UsageEventIn(
                event_id=event_id,
                subscription_id=int(device["subscription_id"]),
                device_id=int(device["device_id"]),
                session_key=session_key,
                protocol="openconnect",
                source_key=f"ocserv:{session_key}"[:220],
                counter_mode="cumulative",
                counter_epoch=session_key[:96],
                source_sequence=sequence,
                uplink_value=tx,
                downlink_value=rx,
                reported_at=now_aware,
            ),
        )
        usage_events += 1

    open_rows = (
        db.query(QuotaSession)
        .filter(
            QuotaSession.node_id == node_id,
            QuotaSession.protocol == "openconnect",
            QuotaSession.status == "active",
        )
        .all()
    )

    closed = 0
    for row in open_rows:
        if row.session_key in active_keys:
            continue
        close_session(
            db,
            node_id,
            SessionCloseIn(
                session_key=row.session_key,
                reason="vpn_session_ended",
            ),
        )
        closed += 1

    return {
        "node_id": node_id,
        "observed": len(observed),
        "matched": len(active_keys),
        "opened": opened,
        "closed": closed,
        "usage_events": usage_events,
        "ignored": ignored,
    }


async def reconcile_quota_runtime_once() -> dict:
    db = SessionLocal()
    results: list[dict] = []

    try:
        nodes = (
            db.query(Node)
            .filter(
                Node.retired_at.is_(None),
                or_(
                    Node.enable_cisco.is_(True),
                    Node.is_mother.is_(True),
                ),
            )
            .order_by(Node.id.asc())
            .all()
        )

        for node in nodes:
            ok, observed, error = await _collect_node_users(node, db)
            if not ok:
                # A failed collector is not evidence that sessions ended.
                # Never close sessions from a failed/ambiguous poll.
                results.append(
                    {
                        "node_id": int(node.id),
                        "ok": False,
                        "error": error or "occtl_unavailable",
                    }
                )
                continue

            try:
                result = _apply_observed_sessions(db, node, observed)
                db.commit()
                results.append({"ok": True, **result})
            except Exception as exc:
                db.rollback()
                results.append(
                    {
                        "node_id": int(node.id),
                        "ok": False,
                        "error": f"{type(exc).__name__}:{str(exc)[:500]}",
                    }
                )

        return {
            "ok": all(item.get("ok") for item in results) if results else True,
            "nodes": results,
        }
    finally:
        db.close()
