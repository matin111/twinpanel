from __future__ import annotations

import asyncio
import json
import re
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


L2TP_TELEMETRY_UP_HOOK = "/etc/ppp/ip-up.d/twinpanel-l2tp-telemetry"
L2TP_TELEMETRY_DOWN_HOOK = "/etc/ppp/ip-down.d/twinpanel-l2tp-telemetry"
L2TP_TELEMETRY_STATE_DIR = "/run/twinpanel/l2tp-sessions"
L2TP_TELEMETRY_MARKER = "TWINPANEL_L2TP_QUOTA_TELEMETRY_V113"

_L2TP_RUNTIME_COMMAND = rf'''set +e
UP={L2TP_TELEMETRY_UP_HOOK!r}
DOWN={L2TP_TELEMETRY_DOWN_HOOK!r}
MARKER={L2TP_TELEMETRY_MARKER!r}

if ! test -x "$UP" \
  || ! test -x "$DOWN" \
  || ! grep -Fq "$MARKER" "$UP" \
  || ! grep -Fq "$MARKER" "$DOWN"
then
  echo "l2tp telemetry hooks unavailable" >&2
  exit 42
fi

python3 - <<'PY'
import glob
import json
import os
import re

state_dir = "/run/twinpanel/l2tp-sessions"
identity_re = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")
iface_re = re.compile(r"^ppp[0-9]+$")

for path in sorted(glob.glob(os.path.join(state_dir, "ppp*"))):
    values = {}

    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.rstrip("\n")
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    except OSError:
        continue

    identity = values.get("identity", "")
    iface = values.get("interface", "")
    remote_ip = values.get("remote_ip", "")
    started_epoch = values.get("started_epoch", "")
    pppd_pid = values.get("pppd_pid", "")

    if not identity_re.fullmatch(identity):
        continue
    if not iface_re.fullmatch(iface):
        continue
    if not remote_ip.startswith("10.94.0."):
        continue

    sysfs = f"/sys/class/net/{iface}/statistics"
    if not os.path.isdir(sysfs):
        continue

    def counter(name):
        try:
            with open(os.path.join(sysfs, name), "r", encoding="ascii") as handle:
                return max(int(handle.read().strip() or "0"), 0)
        except (OSError, ValueError):
            return 0

    print(
        json.dumps(
            {
                "identity": identity,
                "interface": iface,
                "remote_ip": remote_ip,
                "started_epoch": started_epoch,
                "pppd_pid": pppd_pid,
                "uplink": counter("rx_bytes"),
                "downlink": counter("tx_bytes"),
            },
            separators=(",", ":"),
        )
    )
PY'''


def _local_l2tp_runtime() -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["bash", "-lc", _L2TP_RUNTIME_COMMAND],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)

    return proc.returncode == 0, str(proc.stdout or "")


async def _remote_l2tp_runtime(node: Node, db) -> tuple[bool, str]:
    conn = None

    try:
        conn = await ssh_connect_saved(node, db)
        result = await conn.run(
            "bash -lc " + repr(_L2TP_RUNTIME_COMMAND),
            check=False,
            timeout=12,
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


def _parse_l2tp_runtime(raw: str) -> list[dict]:
    sessions: list[dict] = []

    for raw_line in str(raw or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("{"):
            continue

        try:
            payload = json.loads(line)
        except Exception:
            continue

        if not isinstance(payload, dict):
            continue

        identity = str(payload.get("identity") or "").strip()
        interface = str(payload.get("interface") or "").strip()
        remote_ip = str(payload.get("remote_ip") or "").strip()
        started_epoch = str(payload.get("started_epoch") or "").strip()
        pppd_pid = str(payload.get("pppd_pid") or "").strip()

        if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", identity):
            continue
        if not re.fullmatch(r"ppp[0-9]+", interface):
            continue
        if not remote_ip.startswith("10.94.0."):
            continue

        session_identity = ":".join(
            part
            for part in (
                identity,
                interface,
                started_epoch or "current",
                pppd_pid or "pid",
            )
            if part
        )[:140]

        sessions.append(
            {
                "identity": identity,
                "interface": interface,
                "remote_ip": remote_ip,
                "session_identity": session_identity,
                "uplink": max(int(payload.get("uplink") or 0), 0),
                "downlink": max(int(payload.get("downlink") or 0), 0),
            }
        )

    return sessions


async def _collect_l2tp_sessions(
    node: Node,
    db,
) -> tuple[bool, list[dict], str | None]:
    local = bool(getattr(node, "is_mother", False)) or str(
        getattr(node, "agent_url", "") or ""
    ) == "local://core"

    if local:
        ok, output = await asyncio.to_thread(_local_l2tp_runtime)
    else:
        ok, output = await _remote_l2tp_runtime(node, db)

    if not ok:
        return False, [], str(output or "")[-600:]

    try:
        return True, _parse_l2tp_runtime(output), None
    except Exception as exc:
        return False, [], f"l2tp_runtime_parse_failed:{exc}"


def _l2tp_device_map(db, node_id: int) -> dict[str, dict]:
    devices = build_node_devices(db, int(node_id))
    result: dict[str, dict] = {}

    for item in devices:
        if str(item.get("protocol") or "") != "l2tp":
            continue

        identity = str(
            item.get("telemetry_identity")
            or item.get("identity")
            or ""
        ).strip()

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


def _apply_l2tp_sessions(db, node: Node, observed: list[dict]) -> dict:
    node_id = int(node.id)
    devices = _l2tp_device_map(db, node_id)
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
            f"l2tp:{node_id}:{session.get('session_identity') or identity}"
        )[:160]
        active_keys.add(session_key)

        open_result = open_session(
            db,
            node_id,
            SessionOpenIn(
                session_key=session_key,
                subscription_id=subscription_id,
                device_id=device_id,
                protocol="l2tp",
                client_ip=session.get("remote_ip"),
            ),
        )

        if not bool(open_result.get("duplicate")):
            opened += 1

        _touch_session(db, node_id, session_key, now_naive)

        uplink = max(int(session.get("uplink") or 0), 0)
        downlink = max(int(session.get("downlink") or 0), 0)
        sequence = sequence_base + index
        source_key = f"l2tp:{node_id}:{identity}"[:220]
        counter_epoch = session_key[:96]
        event_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                (
                    f"twinpanel:l2tp:{source_key}:{counter_epoch}:"
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
                protocol="l2tp",
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

    open_rows = (
        db.query(QuotaSession)
        .filter(
            QuotaSession.node_id == node_id,
            QuotaSession.protocol == "l2tp",
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
        "collector": "l2tp",
        "node_id": node_id,
        "observed": len(observed),
        "matched": matched,
        "opened": opened,
        "closed": closed,
        "usage_events": usage_events,
        "ignored": ignored,
    }


async def reconcile_l2tp_quota_runtime_once() -> dict:
    db = SessionLocal()
    results: list[dict] = []

    try:
        nodes = (
            db.query(Node)
            .filter(
                Node.retired_at.is_(None),
                Node.enable_l2tp.is_(True),
            )
            .order_by(Node.id.asc())
            .all()
        )

        for node in nodes:
            node_id = int(node.id)
            ok, observed, error = await _collect_l2tp_sessions(node, db)

            # Fail-open: an SSH/hook/collector failure is not authoritative
            # evidence that a PPP session ended. Never close sessions here.
            if not ok:
                results.append(
                    {
                        "collector": "l2tp",
                        "node_id": node_id,
                        "ok": False,
                        "error": error or "l2tp_runtime_unavailable",
                    }
                )
                continue

            try:
                result = _apply_l2tp_sessions(db, node, observed)
                db.commit()
                results.append({"ok": True, **result})

            except Exception as exc:
                db.rollback()
                results.append(
                    {
                        "collector": "l2tp",
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
