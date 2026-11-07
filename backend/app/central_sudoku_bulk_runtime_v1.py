"""Bounded Sudoku service staging over ONE SSH connection.

Sudoku's current revocation model requires one TCP listener/systemd unit per
subscription. This adapter stages at most 64 dedicated instances and starts
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
if not isinstance(incoming,list) or not 1<=len(incoming)<=64:
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
            timeout=30,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if reload.returncode: raise RuntimeError("SUDOKU_DAEMON_RELOAD_FAILED")
    # No unbounded concurrent restarts: only 4 newly created units per wave.
    def enable_one(item):
        sid=item[0];service="twinpanel-sudoku-sub-"+str(sid)+".service"
        result=subprocess.run(["systemctl","enable","--now",service],
            timeout=90,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if result.returncode: raise RuntimeError("SUDOKU_START_FAILED")
        active=subprocess.run(["systemctl","is-active","--quiet",service],
            timeout=15,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if active.returncode: raise RuntimeError("SUDOKU_NOT_ACTIVE")
    for i in range(0,len(newly_created),4):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(enable_one,newly_created[i:i+4]))
    # A systemd Type=simple process may become active just before TCP bind.
    # Allow a bounded listener warm-up, without treating "active" as ready.
    for row in incoming:
        service="twinpanel-sudoku-sub-"+str(row["subscription_id"])+".service"
        ready=False
        for attempt in range(24):
            active=subprocess.run(["systemctl","is-active","--quiet",service],
                timeout=15,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if active.returncode==0:
                with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
                    sock.settimeout(2)
                    ready=sock.connect_ex(("127.0.0.1",row["port"]))==0
            if ready: break
            time.sleep(0.25)
        if not ready:
            raise RuntimeError("SUDOKU_LISTENER_NOT_READY")
except BaseException:
    for sid,port,directory,unit in reversed(newly_created):
        name="twinpanel-sudoku-sub-"+str(sid)+".service"
        subprocess.run(["systemctl","disable","--now",name],timeout=30,
            check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if unit.exists():unit.unlink()
        if directory.exists():shutil.rmtree(directory)
    if newly_created:
        subprocess.run(["systemctl","daemon-reload"],timeout=30,check=False,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
    verify_accounts(accounts)
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
