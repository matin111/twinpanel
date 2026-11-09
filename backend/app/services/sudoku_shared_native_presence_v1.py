"""Read-only, per-identity Sudoku presence for published shared Exits.

Legacy per-subscription services use dedicated TCP ports. A central shared
daemon owns one port for all users, so the old socket-based collector must
NEVER infer individual online states from that shared port.

The locally authenticated Sudoku controller reports exact per-user "conns".
Read its credential only on the Exit, filter/validate the output before SSH,
and consume names (not client keys) in the mother accounting worker.

No runtime mutation, key/whitelist update, quota byte estimate or SSH secret
transfer is performed by this collector.
"""
from __future__ import annotations

import asyncio
import json
import re
import shlex
from typing import Any

from . import modern_quota_runtime_v257 as canonical

MAX_SHARED_USERS = 3000
_MAX_OUTPUT_BYTES = 250_000
_MARKER = "TP_SUDOKU_SHARED_NATIVE_PRESENCE_V1"


def node_collection_command() -> str:
    script = r'''from __future__ import annotations
import json,re,urllib.request
from pathlib import Path

CONF=Path("/etc/twinpanel/standalone/sudoku/shared/server.config.json")
if CONF.is_symlink() or not CONF.is_file():
    raise RuntimeError("SUDOKU_SHARED_CONFIG_UNAVAILABLE")
cfg=json.loads(CONF.read_text(encoding="utf-8"))
token=cfg.get("secret")
expected=cfg.get("users")
if not isinstance(token,str) or not re.fullmatch("[0-9a-f]{48}",token):
    raise RuntimeError("SUDOKU_SHARED_CONTROLLER_NOT_AUTHENTICATED")
if not isinstance(expected,list) or len(expected)>3000:
    raise RuntimeError("SUDOKU_SHARED_CONFIG_WHITELIST_INVALID")
expected_names=set()
for row in expected:
    name=row.get("alias") if isinstance(row,dict) else None
    if not isinstance(name,str) or not re.fullmatch("tp-sub-[1-9][0-9]*",name) or name in expected_names:
        raise RuntimeError("SUDOKU_SHARED_CONFIG_ALIAS_INVALID")
    expected_names.add(name)

req=urllib.request.Request(
    "http://127.0.0.1:19095/users",
    headers={"Authorization":"Bearer "+token},
)
with urllib.request.urlopen(req,timeout=4) as result:
    if result.status!=200:
        raise RuntimeError("SUDOKU_SHARED_CONTROLLER_UNAVAILABLE")
    raw=result.read(600_001)
if len(raw)>600_000:
    raise RuntimeError("SUDOKU_SHARED_CONTROLLER_RESPONSE_TOO_LARGE")
doc=json.loads(raw)
rows=doc.get("users") if isinstance(doc,dict) else None
if (not isinstance(rows,list) or len(rows)>3000
        or type(doc.get("count")) is not int
        or doc["count"]!=len(rows)):
    raise RuntimeError("SUDOKU_SHARED_CONTROLLER_COUNT_INVALID")
names=set();online={};connected=0
for row in rows:
    name=row.get("name") if isinstance(row,dict) else None
    conns=row.get("conns") if isinstance(row,dict) else None
    if (not isinstance(name,str) or not re.fullmatch("tp-sub-[1-9][0-9]*",name)
            or name in names or type(conns) is not int or conns<0 or conns>65535):
        raise RuntimeError("SUDOKU_SHARED_CONTROLLER_USER_INVALID")
    names.add(name)
    if conns>0:
        online[name]=conns
        connected+=conns
if names!=expected_names:
    raise RuntimeError("SUDOKU_SHARED_CONTROLLER_CONFIG_MISMATCH")
# Report only IDs and connection counts; no controller secret, keys or bytes.
print(json.dumps({"marker":"TP_SUDOKU_SHARED_NATIVE_PRESENCE_V1",
                  "names":sorted(names),"online":online,
                  "total":len(names),"connections":connected},
                 separators=(",",":"),ensure_ascii=True))
'''
    return "python3 -c " + shlex.quote(script)


def validate_snapshot(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("marker") != _MARKER:
        raise ValueError("sudoku_shared_native_marker_missing")
    names = payload.get("names")
    online = payload.get("online")
    total = payload.get("total")
    connections = payload.get("connections")
    if (not isinstance(names, list) or not isinstance(online, dict)
            or type(total) is not int or type(connections) is not int
            or total < 0 or total > MAX_SHARED_USERS
            or connections < 0 or len(names) != total):
        raise ValueError("sudoku_shared_native_snapshot_invalid")
    known: set[str] = set()
    for value in names:
        if (not isinstance(value, str)
                or re.fullmatch(r"tp-sub-[1-9][0-9]*", value) is None
                or value in known):
            raise ValueError("sudoku_shared_native_identity_invalid")
        known.add(value)
    summed = 0
    for name, conns in online.items():
        if (name not in known or type(conns) is not int
                or not 1 <= conns <= 65535):
            raise ValueError("sudoku_shared_native_connection_invalid")
        summed += conns
    if summed != connections:
        raise ValueError("sudoku_shared_native_connection_count_mismatch")
    return {"known": known, "online": dict(online),
            "total":total, "connections":connections}


async def collect_shared_native_users(conn) -> tuple[bool, dict[str, Any], str | None]:
    try:
        result = await asyncio.wait_for(
            conn.run(node_collection_command(), check=False, timeout=10),
            timeout=12,
        )
        if int(getattr(result, "exit_status", 1)) != 0:
            raise RuntimeError("native_controller_probe_failed")
        output = str(getattr(result, "stdout", "") or "")
        if not output or len(output.encode("utf-8")) > _MAX_OUTPUT_BYTES:
            raise ValueError("native_controller_response_size_invalid")
        parsed = json.loads(output.strip().splitlines()[-1])
        return True, validate_snapshot(parsed), None
    except (OSError, ValueError, RuntimeError, asyncio.TimeoutError,
            TypeError, KeyError):
        # Never emit raw SSH stderr: it might contain credentials.
        return False, {}, "sudoku_shared_native_snapshot_unavailable"


def apply_shared_native_presence(
    db,
    *,
    node: Any,
    devices: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Only authoritative per-client connections may open a session."""
    if (not isinstance(snapshot, dict)
            or not isinstance(snapshot.get("known"), set)
            or not isinstance(snapshot.get("online"), dict)):
        raise ValueError("sudoku_shared_native_snapshot_unverified")

    now = canonical._utcnow()
    opened = closed = online_count = matched = 0
    known = snapshot["known"]
    by_name = snapshot["online"]
    for device in devices:
        sid = int(device["subscription_id"])
        if sid <= 0:
            raise ValueError("sudoku_shared_native_subscription_invalid")
        name = f"tp-sub-{sid}"
        if name in known:
            matched += 1
        connected = int(by_name.get(name, 0))
        result = canonical._mark_presence(
            db,
            node_id=int(node.id),
            device=device,
            protocol="sudoku",
            online=connected > 0,
            observed_at=now,
            client_ip=None,
            evidence=f"sudoku-native:{name}:conns={connected}",
        )
        opened += result["opened"]
        closed += result["closed"]
        online_count += int(connected > 0)

    return {
        "collector": "sudoku-shared-native-presence",
        "node_id": int(node.id),
        "targets": len(devices),
        "matched": matched,
        "online": online_count,
        "open_connections": int(snapshot["connections"]),
        "opened": opened,
        "closed": closed,
        "usage_events": 0,
        "usage_supported": False,
    }
