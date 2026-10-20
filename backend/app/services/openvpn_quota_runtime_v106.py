from __future__ import annotations

import asyncio
import csv
import socket
import subprocess
import time
import uuid
from datetime import datetime, timezone

from ..database import SessionLocal
from ..models import Node
from ..quota_models import QuotaSession
from ..quota_schemas import SessionCloseIn, SessionOpenIn, UsageEventIn
from ..quota_service import close_session
from ..routers.provision import ssh_connect_saved
from .quota_node_sync import build_node_devices
from .reseller_traffic_pool import apply_usage_event, open_session


OPENVPN_MANAGEMENT_SOCKET = "/run/openvpn-server/twinpanel-mgmt.sock"


_REMOTE_OPENVPN_STATUS_COMMAND = r'''python3 - <<'PY'
import socket

path = "/run/openvpn-server/twinpanel-mgmt.sock"

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.settimeout(3.0)

try:
    sock.connect(path)

    try:
        sock.recv(65536)
    except Exception:
        pass

    sock.sendall(b"status 2\nquit\n")

    chunks = []

    while True:
        try:
            data = sock.recv(65536)
        except socket.timeout:
            break

        if not data:
            break

        chunks.append(data)

        if b"\nEND\n" in data or data.endswith(b"END\n"):
            break

    print(b"".join(chunks).decode("utf-8", errors="replace"), end="")
finally:
    sock.close()
PY'''


def _int_counter(value) -> int:
    try:
        return max(int(str(value or "0").strip()), 0)
    except (TypeError, ValueError):
        return 0


def _query_openvpn_management_local() -> tuple[bool, str]:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(3.0)
        sock.connect(OPENVPN_MANAGEMENT_SOCKET)

        try:
            sock.recv(65536)
        except Exception:
            pass

        sock.sendall(b"status 2\nquit\n")
        chunks: list[bytes] = []

        while True:
            try:
                data = sock.recv(65536)
            except socket.timeout:
                break

            if not data:
                break

            chunks.append(data)

            if b"\nEND\n" in data or data.endswith(b"END\n"):
                break

        sock.close()
        return True, b"".join(chunks).decode("utf-8", errors="replace")

    except Exception as exc:
        try:
            sock.close()
        except Exception:
            pass
        return False, str(exc)


async def _query_openvpn_management_remote(node: Node, db) -> tuple[bool, str]:
    conn = None

    try:
        conn = await ssh_connect_saved(node, db)
        result = await conn.run(
            _REMOTE_OPENVPN_STATUS_COMMAND,
            check=False,
            timeout=8,
        )

        output = str(result.stdout or "")

        if result.stderr:
            output = (output + "\n" + str(result.stderr)).strip()

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


def _parse_openvpn_status(raw: str) -> list[dict]:
    sessions: list[dict] = []

    for raw_line in str(raw or "").splitlines():
        if not raw_line.startswith("CLIENT_LIST,"):
            continue

        try:
            row = next(csv.reader([raw_line]))
        except Exception:
            continue

        if len(row) < 9:
            continue

        common_name = str(row[1] or "").strip()

        if not common_name or common_name == "UNDEF":
            continue

        connected_since = str(row[7] or "").strip()
        connected_epoch = str(row[8] or "").strip()
        client_id = str(row[10] or "").strip() if len(row) > 10 else ""

        session_identity = ":".join(
            part
            for part in (
                common_name,
                connected_epoch or connected_since or "current",
                client_id or "client",
            )
            if part
        )

        sessions.append(
            {
                "identity": common_name,
                "session_identity": session_identity[:140],
                # OpenVPN management reports bytes received by the server
                # from the client and bytes sent by the server to the client.
                "uplink": _int_counter(row[5] if len(row) > 5 else 0),
                "downlink": _int_counter(row[6] if len(row) > 6 else 0),
            }
        )

    return sessions


async def _collect_openvpn_sessions(
    node: Node,
    db,
) -> tuple[bool, list[dict], str | None]:
    local = bool(getattr(node, "is_mother", False)) or str(
        getattr(node, "agent_url", "") or ""
    ) == "local://core"

    if local:
        ok, output = await asyncio.to_thread(_query_openvpn_management_local)
    else:
        ok, output = await _query_openvpn_management_remote(node, db)

    if not ok:
        return False, [], str(output or "")[-600:]

    try:
        return True, _parse_openvpn_status(output), None
    except Exception as exc:
        return False, [], f"openvpn_status_parse_failed:{exc}"


def _openvpn_device_map(db, node_id: int) -> dict[str, dict]:
    devices = build_node_devices(db, int(node_id))
    result: dict[str, dict] = {}

    for item in devices:
        if str(item.get("protocol") or "") != "openvpn":
            continue

        # Exact runtime mapping only. Do not guess or fall back to the generic
        # credential username: legacy EasyRSA CNs and Central-PKI CNs differ.
        identity = str(item.get("telemetry_identity") or "").strip()

        if identity:
            result[identity] = item

    return result


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


def _apply_openvpn_sessions(db, node: Node, observed: list[dict]) -> dict:
    node_id = int(node.id)
    devices = _openvpn_device_map(db, node_id)
    now_aware = datetime.now(timezone.utc)
    now_naive = now_aware.replace(tzinfo=None)
    sequence_base = int(time.time_ns() // 1_000_000)

    opened = 0
    closed = 0
    usage_events = 0
    ignored = 0
    matched = 0
    active_keys: set[str] = set()

    for index, session in enumerate(observed):
        identity = str(session.get("identity") or "").strip()
        device = devices.get(identity)

        if device is None:
            ignored += 1
            continue

        matched += 1
        subscription_id = int(device["subscription_id"])
        device_id = int(device["device_id"])
        session_key = (
            f"openvpn:{node_id}:{session.get('session_identity') or identity}"
        )[:160]
        active_keys.add(session_key)

        open_result = open_session(
            db,
            node_id,
            SessionOpenIn(
                session_key=session_key,
                subscription_id=subscription_id,
                device_id=device_id,
                protocol="openvpn",
                client_ip=None,
            ),
        )

        if not bool(open_result.get("duplicate")):
            opened += 1

        _touch_session(db, node_id, session_key, now_naive)

        uplink = max(int(session.get("uplink") or 0), 0)
        downlink = max(int(session.get("downlink") or 0), 0)
        sequence = sequence_base + index
        source_key = f"openvpn:{node_id}:{identity}"[:220]
        counter_epoch = session_key[:96]
        event_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    f"twinpanel:openvpn:{source_key}:{counter_epoch}:"
                    f"{sequence}:{uplink}:{downlink}"
                ),
            )
        )

        apply_usage_event(
            db,
            node_id,
            UsageEventIn(
                event_id=event_id,
                subscription_id=subscription_id,
                device_id=device_id,
                session_key=session_key,
                protocol="openvpn",
                source_key=source_key,
                counter_mode="cumulative",
                counter_epoch=counter_epoch,
                source_sequence=sequence,
                uplink_value=uplink,
                downlink_value=downlink,
                reported_at=now_aware,
            ),
        )
        usage_events += 1

    # Only a successful management poll is allowed to close sessions. Collector
    # errors return before this function is called, so telemetry/API failures can
    # never tear down or falsely close a live OpenVPN session.
    open_rows = (
        db.query(QuotaSession)
        .filter(
            QuotaSession.node_id == node_id,
            QuotaSession.protocol == "openvpn",
            QuotaSession.status == "active",
        )
        .all()
    )

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
        "collector": "openvpn",
        "node_id": node_id,
        "observed": len(observed),
        "matched": matched,
        "opened": opened,
        "closed": closed,
        "usage_events": usage_events,
        "ignored": ignored,
    }


async def reconcile_openvpn_quota_runtime_once() -> dict:
    db = SessionLocal()
    results: list[dict] = []

    try:
        nodes = (
            db.query(Node)
            .filter(
                Node.retired_at.is_(None),
                Node.enable_openvpn.is_(True),
            )
            .order_by(Node.id.asc())
            .all()
        )

        for node in nodes:
            node_id = int(node.id)
            ok, observed, error = await _collect_openvpn_sessions(node, db)

            if not ok:
                results.append(
                    {
                        "collector": "openvpn",
                        "node_id": node_id,
                        "ok": False,
                        "error": error or "openvpn_management_unavailable",
                    }
                )
                continue

            try:
                result = _apply_openvpn_sessions(db, node, observed)
                db.commit()
                results.append({"ok": True, **result})

            except Exception as exc:
                db.rollback()
                results.append(
                    {
                        "collector": "openvpn",
                        "node_id": node_id,
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
