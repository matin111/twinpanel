"""Bounded Sudoku service staging over ONE SSH connection.

Sudoku's current revocation model requires one TCP listener/systemd unit per
subscription. This adapter stages at most 3000 dedicated instances and starts
them in controlled groups. It does NOT assert 1900-user capacity or 3-minute
activation. It never restarts existing instances, and never publishes nodes.
Only master *public* keys are sent to the node, not client private keys.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from .services.central_sudoku_capacity_v1 import (
    MAX_LEGACY_SUDOKU_SERVICES, sudoku_port,
)


def verify_accounts(accounts: list[dict]) -> None:
    if not isinstance(accounts,list) or not 1<=len(accounts)<=MAX_LEGACY_SUDOKU_SERVICES:
        raise ValueError("SUDOKU_BULK_CAPACITY_EXCEEDED")
    ids=set(); ports=set()
    for item in accounts:
        if not isinstance(item,dict):
            raise ValueError("SUDOKU_BULK_INVALID_ROW")
        sid=item.get("subscription_id")
        port=item.get("port")
        master=item.get("master_public")
        if not isinstance(sid,int) or sid<=0 or sid in ids:
            raise ValueError("SUDOKU_BULK_INVALID_ID")
        if type(port) is not int or port!=sudoku_port(sid) or port in ports:
            raise ValueError("SUDOKU_BULK_INVALID_PORT")
        if not isinstance(master,str) or not 32<=len(master)<=512 or any(c not in "0123456789abcdefABCDEF" for c in master):
            raise ValueError("SUDOKU_BULK_INVALID_PUBLIC_KEY")
        ids.add(sid);ports.add(port)


def remote_source(*, base="/etc/twinpanel/standalone/sudoku/subscriptions",
                  unit_dir="/etc/systemd/system",
                  program="/usr/local/bin/twinpanel-sudoku") -> str:
    src=r'''import concurrent.futures
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BASE=Path(__BASE__)
UNIT_DIR=Path(__UNIT__)
PROGRAM=Path(__PROGRAM__)
incoming=json.load(sys.stdin)
if not isinstance(incoming,list) or not 1<=len(incoming)<=3000:
    raise SystemExit("SUDOKU_BULK_COUNT")
if not PROGRAM.is_file() or PROGRAM.is_symlink():
    raise SystemExit("SUDOKU_RUNTIME_MISSING")
seen=set();ports=set()
for row in incoming:
    sid=row.get("subscription_id")
    port=row.get("port")
    master=row.get("master_public")
    if (not isinstance(sid,int) or sid<=0 or sid in seen
        or not isinstance(port,int) or port!=30000+((sid-1)%30000)
        or port in ports or not isinstance(master,str)
        or not 32<=len(master)<=512 or not re.fullmatch("[0-9a-fA-F]+",master)):
        raise SystemExit("SUDOKU_BULK_INVALID_RECORD")
    seen.add(sid);ports.add(port)
if BASE.is_symlink() or UNIT_DIR.is_symlink():
    raise SystemExit("SUDOKU_UNSAFE_BASE")
# Strict resource admission on the TARGET node, not the controller.
# Running Sudoku averages ~10 MB RSS in an observed installation; reserve
# 16 MiB per additional process and 512 MiB headroom. No network mutations
# or filesystem writes occur before this check.
new_count=sum(
    1 for row in incoming
    if not (UNIT_DIR/("twinpanel-sudoku-sub-"+str(row["subscription_id"])+".service")).exists()
)
meminfo={}
for line in Path("/proc/meminfo").read_text().splitlines():
    bits=line.split()
    if len(bits)>=2 and bits[0].endswith(":"):
        try:meminfo[bits[0][:-1]]=int(bits[1])
        except ValueError:pass
available_kib=meminfo.get("MemAvailable",0)
minimum_kib=512*1024 + new_count*16*1024
if available_kib<minimum_kib:
    raise SystemExit("SUDOKU_TARGET_MEMORY_ADMISSION_FAILED")
installed_count=sum(1 for _ in UNIT_DIR.glob("twinpanel-sudoku-sub-*.service"))
if installed_count+new_count>3000:
    raise SystemExit("SUDOKU_TARGET_SERVICE_CAPACITY_EXCEEDED")
BASE.mkdir(parents=True,exist_ok=True)
newly_created=[]
try:
    for row in incoming:
        sid=row["subscription_id"];port=row["port"]
        directory=BASE/str(sid)
        config=directory/"server.config.json"
        marker=directory/"subscription-id"
        unit=UNIT_DIR/("twinpanel-sudoku-sub-"+str(sid)+".service")
        if directory.is_symlink() or config.is_symlink() or unit.is_symlink():
            raise RuntimeError("SUDOKU_SYMLINK")
        if directory.exists() or unit.exists():
            if not marker.is_file() or marker.read_text().strip()!=str(sid):
                raise RuntimeError("SUDOKU_OWNERSHIP_CONFLICT")
            if not config.is_file() or not unit.is_file():
                raise RuntimeError("SUDOKU_INCOMPLETE_EXISTING_SERVICE")
            existing=json.loads(config.read_text())
            if existing.get("local_port")!=port or existing.get("key")!=row["master_public"]:
                raise RuntimeError("SUDOKU_EXISTING_CONFIG_CONFLICT")
            continue
        # Validate no outside listener owns the desired TCP port.
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try: sock.bind(("0.0.0.0",port))
            except OSError: raise RuntimeError("SUDOKU_PORT_IN_USE")
        directory.mkdir(mode=0o700)
        # Register rollback ownership before any file write can fail.
        newly_created.append((sid,port,directory,unit))
        server={
            "mode":"server","transport":"tcp","local_port":port,
            "fallback_address":"127.0.0.1:80","key":row["master_public"],
            "aead":"chacha20-poly1305","suspicious_action":"fallback",
            "padding_min":5,"padding_max":15,"custom_table":"",
            "custom_tables":[],"ascii":"prefer_entropy",
            "enable_pure_downlink":True,"multiplex":"off",
            "httpmask":{"disable":False,"mode":"auto","tls":False,
                        "host":"","path_root":""},"reverse":{"listen":""},
        }
        config.write_text(json.dumps(server,ensure_ascii=False,indent=2)+"\n")
        os.chmod(config,0o600)
        marker.write_text(str(sid)+"\n")
        os.chmod(marker,0o600)
        body=(
            "[Unit]\nDescription=TwinPanel Sudoku subscription "+str(sid)+
            "\nAfter=network-online.target\nWants=network-online.target"+
            "\n[Service]\nType=simple\nUser=root\nExecStart="+
            str(PROGRAM)+" -c "+str(config)+
            "\nRestart=on-failure\nRestartSec=3"+
            "\nLimitNOFILE=1048576\n[Install]"+
            "\nWantedBy=multi-user.target\n"
        )
        unit.write_text(body)
        os.chmod(unit,0o644)
    if newly_created:
        reload=subprocess.run(["systemctl","daemon-reload"],
            timeout=40,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if reload.returncode: raise RuntimeError("SUDOKU_DAEMON_RELOAD_FAILED")
        # One systemd transaction for the whole desired state, never a
        # systemctl invocation for each subscription or a four-user wave.
        units=["twinpanel-sudoku-sub-"+str(sid)+".service"
               for sid,_,_,_ in newly_created]
        enabled=subprocess.run(["systemctl","enable",*units],timeout=120,
            check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if enabled.returncode: raise RuntimeError("SUDOKU_ENABLE_SET_FAILED")
        started=subprocess.run(["systemctl","start","--no-block",*units],
            timeout=90,check=False,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        if started.returncode: raise RuntimeError("SUDOKU_START_SET_FAILED")
    # Check the whole desired set using a single systemd state listing per
    # poll, rather than hundreds of per-user status commands. Socket checks
    # are local to the node, not controller-to-node SSH operations.
    pending={row["subscription_id"]:row["port"] for row in incoming}
    deadline=time.monotonic()+90
    while pending and time.monotonic()<deadline:
        states=subprocess.run(["systemctl","list-units","--type=service",
            "--state=running","--no-legend","--plain"],capture_output=True,
            text=True,timeout=20,check=False)
        if states.returncode:raise RuntimeError("SUDOKU_SERVICE_AUDIT_FAILED")
        active={line.split()[0] for line in states.stdout.splitlines()
                if line.split()}
        for sid,port in list(pending.items()):
            service="twinpanel-sudoku-sub-"+str(sid)+".service"
            if service not in active:continue
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
                sock.settimeout(0.35)
                if sock.connect_ex(("127.0.0.1",port))==0:
                    del pending[sid]
        if pending:time.sleep(0.4)
    if pending:
        raise RuntimeError("SUDOKU_DESIRED_LISTENERS_NOT_READY")
except BaseException:
    # Roll back only units THIS call created. One systemd transaction per
    # operation; pre-existing subscriber units are never stopped or removed.
    if newly_created:
        units=["twinpanel-sudoku-sub-"+str(sid)+".service"
               for sid,_,_,_ in newly_created]
        subprocess.run(["systemctl","stop",*units],timeout=90,
            check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(["systemctl","disable",*units],timeout=90,
            check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _,_,directory,unit in reversed(newly_created):
            if unit.exists():unit.unlink()
            if directory.exists():shutil.rmtree(directory)
        subprocess.run(["systemctl","daemon-reload"],timeout=40,
            check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    raise
print(json.dumps({"ok":True,"applied":len(incoming),
                  "new_units":len(newly_created)},separators=(",",":")))
'''
    for key,val in {
        "__BASE__":repr(base),"__UNIT__":repr(unit_dir),
        "__PROGRAM__":repr(program),
    }.items():src=src.replace(key,val)
    return src


async def apply_bulk(conn: Any, accounts: list[dict]) -> dict:
    # Decommissioned: this V1 adapter creates ONE systemd unit per client.
    # The V2 shared node daemon must be the only live Sudoku installer.
    # Fail before opening an SSH process, touching account state or sending keys.
    raise RuntimeError("SUDOKU_LEGACY_BULK_DISABLED_USE_SHARED_V2")
    encoded=base64.b64encode(remote_source().encode()).decode("ascii")
    process=await asyncio.wait_for(
        conn.create_process("python3 -c \"$(printf '%s' '"+encoded+"' | base64 -d)\""),
        timeout=25,
    )
    process.stdin.write(json.dumps(accounts))
    process.stdin.write_eof()
    result=await asyncio.wait_for(process.wait(),timeout=900)
    if result.exit_status:
        raise RuntimeError("SUDOKU_BULK_REMOTE_FAILURE")
    try:
        ack=json.loads((result.stdout or "").strip().splitlines()[-1])
    except (ValueError,IndexError) as exc:
        raise RuntimeError("SUDOKU_BULK_ACK_MISSING") from exc
    if ack.get("ok") is not True or ack.get("applied")!=len(accounts):
        raise RuntimeError("SUDOKU_BULK_ACK_MISMATCH")
    return ack
