"""Real, read-only per-subscription traffic for the retired legacy Sudoku units.

Each existing dedicated Sudoku unit owns exactly one subscription's proxy
process. systemd cgroup IPIngressBytes counts incoming wire bytes at that
process (both client uploads and upstream downloads). Unlike an open TCP
socket or estimated speed, these are kernel counters. Enable accounting on
the *already running* owned service without restarting it; first observation
of each unit invocation is a zero-charge baseline. Never touch shared Sudoku,
firewall, credentials, or other protocol units.
"""
from __future__ import annotations

import asyncio
import json
import re
import shlex
from typing import Any

from . import modern_quota_runtime_v257 as canonical

MAX_UNITS = 3000

# Executed only on the already-authenticated legacy Exit management SSH link.
# JSON argument contains only verified subscription IDs and assigned ports.
_REMOTE = r'''import json,sys,re,subprocess
from pathlib import Path
requested=json.loads(sys.argv[1])
if not isinstance(requested,list) or len(requested)>3000:
    raise RuntimeError("SUDOKU_LEGACY_INVALID_REQUEST")
if any(type(item)!=dict or type(item.get("sid"))!=int
       or type(item.get("port"))!=int or item["sid"]<=0
       or not 1<=item["port"]<=65535 for item in requested):
    raise RuntimeError("SUDOKU_LEGACY_INVALID_IDENTITY")
if len({item["sid"] for item in requested})!=len(requested):
    raise RuntimeError("SUDOKU_LEGACY_DUPLICATE_IDENTITY")
boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip().replace("-","")
if not re.fullmatch("[0-9a-f]{32}",boot):
    raise RuntimeError("SUDOKU_LEGACY_BOOT_ID_INVALID")

def properties(unit):
    result=subprocess.run(["systemctl","show",unit,
        "-p","MainPID","-p","ActiveState","-p","IPAccounting",
        "-p","IPIngressBytes","-p","InvocationID","-p","FragmentPath"],
        capture_output=True,text=True,check=False,timeout=8)
    if result.returncode:
        return {}
    return dict(line.split("=",1) for line in result.stdout.splitlines()
                if "=" in line)

out=[]
for item in requested:
    sid=item["sid"];port=item["port"]
    unit=f"twinpanel-sudoku-sub-{sid}.service"
    unit_file=Path("/etc/systemd/system")/unit
    config=Path(f"/etc/twinpanel/standalone/sudoku/subscriptions/{sid}/server.config.json")
    if (unit_file.is_symlink() or config.is_symlink()
            or not unit_file.is_file() or not config.is_file()):
        continue
    # Fail closed if the unit is no longer the expected subscription daemon.
    expected=f"ExecStart=/usr/local/bin/twinpanel-sudoku -c {config}"
    if expected not in unit_file.read_text().splitlines():
        continue
    try:
        cfg=json.loads(config.read_text())
        if cfg.get("mode")!="server" or type(cfg.get("local_port")) is not int or cfg["local_port"]!=port:
            continue
    except (ValueError,OSError,TypeError):
        continue
    before=properties(unit)
    if (before.get("FragmentPath")!=str(unit_file)
            or before.get("ActiveState")!="active"
            or not before.get("MainPID","").isdigit()
            or int(before["MainPID"])<=0):
        continue
    if before.get("IPAccounting")!="yes":
        # systemctl set-property applies live, does not restart the daemon.
        enabled=subprocess.run(["systemctl","set-property","--runtime",unit,
                                "IPAccounting=yes"],capture_output=True,
                               text=True,check=False,timeout=12)
        if enabled.returncode:
            continue
    after=properties(unit)
    invocation=after.get("InvocationID","")
    ingress=after.get("IPIngressBytes","")
    if (after.get("ActiveState")!="active"
            or after.get("MainPID")!=before.get("MainPID")
            or after.get("IPAccounting")!="yes"
            or not re.fullmatch("[0-9a-f]{32}",invocation)
            or not re.fullmatch("[0-9]{1,20}",ingress)
            or int(ingress)>2**63-1):
        continue
    out.append({"sid":sid,"port":port,"epoch":boot+":"+invocation,
                "ingress":int(ingress)})
print(json.dumps({"marker":"TP_SUDOKU_LEGACY_IPACCOUNTING_V1",
                  "counters":out},separators=(",",":")))
'''


def eligible_legacy_units(devices: list[dict[str, Any]]) -> list[dict[str, int]]:
    identities: dict[int, int] = {}
    for item in devices:
        try:
            sid = int(item["subscription_id"])
            identity = str(item.get("telemetry_identity") or item.get("identity") or "")
            port = canonical._sudoku_port(identity)
            if sid > 0 and port and sid not in identities:
                identities[sid] = port
        except (ValueError, TypeError, KeyError):
            continue
    return [{"sid": sid, "port": port} for sid, port in sorted(identities.items())][:MAX_UNITS]


def validate_counters(payload: Any, units: list[dict[str, int]]) -> dict[int, dict[str, Any]]:
    if (not isinstance(payload, dict)
            or payload.get("marker")!="TP_SUDOKU_LEGACY_IPACCOUNTING_V1"
            or not isinstance(payload.get("counters"),list)):
        raise ValueError("sudoku_legacy_metrics_invalid")
    expected={int(row["sid"]):int(row["port"]) for row in units}
    parsed: dict[int, dict[str, Any]]={}
    for row in payload["counters"]:
        if not isinstance(row,dict):
            raise ValueError("sudoku_legacy_metrics_invalid")
        sid=row.get("sid");port=row.get("port")
        epoch=row.get("epoch");ingress=row.get("ingress")
        if (type(sid) is not int or sid not in expected
                or type(port) is not int or expected[sid]!=port
                or sid in parsed or not isinstance(epoch,str)
                or re.fullmatch(r"[0-9a-f]{32}:[0-9a-f]{32}",epoch) is None
                or type(ingress) is not int or not 0<=ingress<=2**63-1):
            raise ValueError("sudoku_legacy_metrics_invalid")
        parsed[sid]={"epoch":epoch,"ingress":ingress}
    return parsed


async def collect_legacy_unit_counters(conn, devices: list[dict[str, Any]]) -> tuple[bool,dict[int,dict],str|None]:
    units=eligible_legacy_units(devices)
    if not units:
        return True,{} ,None
    command="python3 -c "+shlex.quote(_REMOTE)+" "+shlex.quote(json.dumps(units,separators=(",",":")))
    try:
        result=await asyncio.wait_for(conn.run(command,check=False,timeout=30),timeout=33)
        if int(getattr(result,"exit_status",1)):
            raise RuntimeError("sudoku_legacy_metrics_unavailable")
        raw=str(getattr(result,"stdout","") or "").strip()
        if not raw or len(raw)>200000:
            raise ValueError("sudoku_legacy_metrics_size_invalid")
        return True,validate_counters(json.loads(raw.splitlines()[-1]),units),None
    except (RuntimeError,ValueError,TypeError,OSError,asyncio.TimeoutError):
        # Never print remote stderr or secrets/configuration.
        return False,{},"sudoku_legacy_metrics_unavailable"


def apply_legacy_unit_counters(db, *, node, devices: list[dict[str,Any]],
                               counters: dict[int,dict[str,Any]]) -> dict[str,Any]:
    """Bill only kernel-observed per-subscription ingress delta, never presence."""
    from ..models import Subscription, SubscriptionStatus
    now=canonical._utcnow()
    seen:set[int]=set()
    baselined=events=accepted=rejected=0
    for device in devices:
        sid=int(device["subscription_id"])
        if sid in seen:
            continue
        seen.add(sid)
        counter=counters.get(sid)
        if counter is None:
            continue
        sub=db.get(Subscription,sid)
        if not sub or sub.status!=SubscriptionStatus.ACTIVE:
            continue
        active=canonical._active_sessions(
            db,node_id=int(node.id),device_id=int(device["device_id"]),
            protocol="sudoku",
        )
        try:
            reading=canonical._baseline_or_apply_cumulative(
                db,node_id=int(node.id),device=device,protocol="sudoku",
                # InvocationID (plus boot) changes on daemon restart; a new
                # source key guarantees a zero-charge baseline after restart.
                source_key=f"sudoku:legacy:{sid}:{counter['epoch']}",
                counter_epoch=counter["epoch"],
                uplink=int(counter["ingress"]),downlink=0,
                session_key=active[0].session_key if active else None,
                client_ip=None,reported_at=now,
            )
        except (RuntimeError, ValueError) as exc:
            if str(exc) not in ("counter_decreased_without_authoritative_new_epoch",
                                "runtime_counter_source_identity_conflict"):
                raise
            rejected+=1
            continue
        baselined+=int(bool(reading["baselined"]))
        events+=int(bool(reading["event"]))
        accepted+=int(reading["accepted_bytes"])
    return {"collector":"sudoku-legacy-systemd-ingress","matched":len(counters),
            "baselined":baselined,"usage_events":events,
            "accepted_bytes":accepted,"rejected_counters":rejected,
            "usage_supported":bool(counters)}
