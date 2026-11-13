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

from fastapi import HTTPException

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
# The upstream authenticated controller has authoritative per-user
# cumulative wire counters. Validate them ON THE EXIT before SSH transport.
# Bind each reading to the daemon invocation so restarts get a fresh baseline.
import subprocess
service=subprocess.run(
    ["systemctl","show","twinpanel-sudoku-shared.service",
     "-p","ActiveState","-p","MainPID","-p","InvocationID"],
    capture_output=True,text=True,check=False,timeout=5)
properties=dict(line.split("=",1) for line in service.stdout.splitlines() if "=" in line)
epoch=properties.get("InvocationID","")
if (service.returncode or properties.get("ActiveState")!="active"
        or not properties.get("MainPID","").isdigit()
        or int(properties["MainPID"])<=0
        or not re.fullmatch("[0-9a-f]{32}",epoch)):
    raise RuntimeError("SUDOKU_SHARED_EPOCH_UNAVAILABLE")
names=set();online={};connected=0;counters={}
for row in rows:
    name=row.get("name") if isinstance(row,dict) else None
    conns=row.get("conns") if isinstance(row,dict) else None
    up=row.get("upTotal") if isinstance(row,dict) else None
    down=row.get("downTotal") if isinstance(row,dict) else None
    used=row.get("used") if isinstance(row,dict) else None
    if (not isinstance(name,str) or not re.fullmatch("tp-sub-[1-9][0-9]*",name)
            or name in names or type(conns) is not int or not 0<=conns<=65535
            or type(up) is not int or not 0<=up<=2**63-1
            or type(down) is not int or not 0<=down<=2**63-1
            or type(used) is not int or not 0<=used<=2**63-1):
        raise RuntimeError("SUDOKU_SHARED_CONTROLLER_USER_INVALID")
    names.add(name)
    # The controller's "used" policy field can lag independent up/down\n    # counters mid-update; validate its type, but bill from upTotal/downTotal.\n    # Zero-traffic subscribers need no quota cursor: shared Exit whitelists
    # may contain thousands of users with no activity.
    if used>0:
        counters[name]={"up":up,"down":down}
    if conns>0:
        online[name]=conns
        connected+=conns
if names!=expected_names:
    raise RuntimeError("SUDOKU_SHARED_CONTROLLER_CONFIG_MISMATCH")
# Never expose keys/secret or arbitrary controller metadata.
print(json.dumps({"marker":"TP_SUDOKU_SHARED_NATIVE_PRESENCE_V1",
                  "names":sorted(names),"online":online,
                  "total":len(names),"connections":connected,
                  "epoch":epoch,"counters":counters},
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
    epoch = payload.get("epoch")
    counters = payload.get("counters")
    if (epoch is None and counters is None):
        # Backward-compatible presence-only snapshots used by existing tests.
        # Never charge bytes when the runtime provides no counter evidence.
        validated_counters = {}
        validated_epoch = None
    else:
        if (not isinstance(epoch,str)
                or re.fullmatch(r"[0-9a-f]{32}",epoch) is None
                or not isinstance(counters,dict)
                or not set(counters).issubset(known)):
            raise ValueError("sudoku_shared_native_counters_invalid")
        validated_counters = {}
        for name, reading in counters.items():
            if not isinstance(reading,dict) or set(reading)!={"up","down"}:
                raise ValueError("sudoku_shared_native_counter_fields_invalid")
            up,down = reading["up"],reading["down"]
            if (type(up) is not int or type(down) is not int
                    or min(up,down)<0 or up+down>2**63-1):
                raise ValueError("sudoku_shared_native_counter_values_invalid")
            validated_counters[name]={"up":up,"down":down}
        validated_epoch=epoch
    return {"known": known, "online": dict(online),
            "total":total, "connections":connections,
            "epoch":validated_epoch,"counters":validated_counters}


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
        try:
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
        except HTTPException as exc:
            if exc.status_code == 403 and str(exc.detail) == "subscription_not_active":
                continue
            raise
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

def apply_shared_native_counters(
    db,
    *,
    node: Any,
    devices: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Bill only per-user authenticated cumulative wire deltas.

    A new daemon invocation has a new source key, so its first reading is
    non-billable even if the daemon ran before the accounting worker started.
    Counter resets within an invocation fail closed; no usage is fabricated
    from presence, speed, or connection counts.
    """
    epoch=snapshot.get("epoch")
    counters=snapshot.get("counters")
    if not epoch or not isinstance(counters,dict) or not counters:
        return {"usage_supported":False,"usage_events":0,
                "accepted_bytes":0,"baselined":0,"rejected_counters":0}
    from ..models import Subscription, SubscriptionStatus
    now=canonical._utcnow()
    baselined=events=accepted=rejected=0
    seen=set()
    for device in devices:
        sid=int(device["subscription_id"])
        if sid in seen:
            continue
        seen.add(sid)
        name=f"tp-sub-{sid}"
        counter=counters.get(name)
        if counter is None:
            continue
        sub=db.get(Subscription,sid)
        if sub is None or sub.status!=SubscriptionStatus.ACTIVE:
            continue
        active=canonical._active_sessions(
            db,node_id=int(node.id),device_id=int(device["device_id"]),
            protocol="sudoku",
        )
        try:
            reading=canonical._baseline_or_apply_cumulative(
                db,node_id=int(node.id),device=device,protocol="sudoku",
                source_key=f"sudoku:shared:{sid}:{epoch}",
                counter_epoch=epoch,
                uplink=counter["up"],downlink=counter["down"],
                session_key=active[0].session_key if active else None,
                client_ip=None,reported_at=now,
            )
        except RuntimeError as exc:
            if str(exc) not in (
                "counter_decreased_without_authoritative_new_epoch",
                "runtime_counter_source_identity_conflict",
            ):
                raise
            rejected+=1
            continue
        baselined+=int(bool(reading["baselined"]))
        events+=int(bool(reading["event"]))
        accepted+=int(reading["accepted_bytes"])
    return {"usage_supported":True,"usage_events":events,
            "accepted_bytes":accepted,"baselined":baselined,
            "rejected_counters":rejected}
