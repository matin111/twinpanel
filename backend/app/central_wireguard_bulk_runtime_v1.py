"""Atomic one-session WireGuard peer projection for a staged Exit.

Only public keys cross to the node. Client private keys are generated and
encrypted in the controller, never emitted in logs or remote process output.
Uses wg syncconf ONCE, preserving the live interface and existing sessions.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


def new_keypair() -> tuple[str,str]:
    key=X25519PrivateKey.generate()
    secret=base64.b64encode(key.private_bytes(
        serialization.Encoding.Raw,serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )).decode("ascii")
    public=base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw,serialization.PublicFormat.Raw,
    )).decode("ascii")
    return secret,public


def remote_script(
    *,
    config_path="/etc/wireguard/wg-access0.conf",
    interface="wg-access0",
    lock_path="/run/twinpanel-wg-allocation.lock",
) -> str:
    src=r'''import base64
import fcntl
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CONF=Path(__CONF__)
IFACE=__IFACE__
LOCK=Path(__LOCK__)
payload=json.load(sys.stdin)
incoming=payload.get("peers")
if not isinstance(incoming,list) or not 0 < len(incoming) <= 3000:
    raise SystemExit("INVALID_WG_BULK_PAYLOAD")
peers={}
for item in incoming:
    sid=item.get("id")
    public=item.get("public")
    if not isinstance(sid,int) or sid<1 or sid in peers:
        raise SystemExit("DUPLICATE_WG_SUBSCRIPTION")
    try:
        pub_bytes=base64.b64decode(public,validate=True)
    except Exception:
        raise SystemExit("INVALID_WG_PUBLIC_KEY")
    if len(pub_bytes)!=32:
        raise SystemExit("INVALID_WG_PUBLIC_KEY")
    peers[sid]=public
if len(set(peers.values()))!=len(peers):
    raise SystemExit("DUPLICATE_WG_PUBLIC_KEY")
if CONF.is_symlink() or not CONF.is_file():
    raise SystemExit("WG_CONFIG_UNSAFE")
LOCK.parent.mkdir(parents=True,exist_ok=True)
with open(LOCK,"a+") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    original=CONF.read_text(encoding="utf-8")
    addr_line=re.search(r"(?m)^\s*Address\s*=\s*(.+)$",original)
    if not addr_line or "10.96.0.1/21" not in addr_line.group(1):
        raise SystemExit("WG_NODE_ADDRESS_POOL_NOT_CONFIGURED")
    live_addr=subprocess.run(["ip","-4","-o","addr","show",IFACE],
        capture_output=True,text=True,check=False,timeout=8)
    if live_addr.returncode or "10.96.0.1/21" not in live_addr.stdout:
        raise SystemExit("WG_ADDRESS_POOL_NOT_LIVE")
    default=subprocess.run(["ip","-4","route","show","default"],
        capture_output=True,text=True,check=False,timeout=8)
    interface_match=re.search(r"\bdev\s+(\S+)",default.stdout)
    if default.returncode or not interface_match:
        raise SystemExit("WG_PUBLIC_EGRESS_ROUTE_NOT_READY")
    public_dev=interface_match.group(1)
    for network in ("10.93.0.0/24","10.96.0.0/21"):
        nat=subprocess.run(
            ["iptables","-t","nat","-C","POSTROUTING","-s",network,
             "-o",public_dev,"-j","MASQUERADE"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            timeout=8,check=False,
        )
        if nat.returncode:
            raise SystemExit("WG_PUBLIC_EGRESS_NAT_NOT_READY")
    existing=subprocess.run(["wg","show",IFACE,"peers"],
        capture_output=True,text=True,check=False,timeout=8)
    if existing.returncode:
        raise SystemExit("WG_INTERFACE_OFFLINE")
    live_peers={x.strip() for x in existing.stdout.splitlines() if x.strip()}
    # If a peer was added outside the saved config, syncconf could drop it.
    stored_keys=set(re.findall(r"(?m)^\s*PublicKey\s*=\s*(\S+)",original))
    if not live_peers.issubset(stored_keys):
        raise SystemExit("WG_LIVE_PEER_NOT_PERSISTED")
    parts=re.split(r"(?m)^(?=\[Peer\]\s*$)",original)
    base=parts[0]
    if not base.lstrip().startswith("[Interface]"):
        raise SystemExit("WG_INTERFACE_CONFIG_INVALID")
    unmanaged=[]
    managed={}
    taken=set()
    for part in parts[1:]:
        marker=re.search(r"(?m)^# TwinPanel-central subscription=(\d+)\s*$",part)
        addr=re.search(r"(?m)^\s*AllowedIPs\s*=\s*([^\s,]+)",part)
        if addr:
            try:
                taken.add(str(ipaddress.ip_interface(addr.group(1)).ip))
            except ValueError:
                raise SystemExit("WG_EXISTING_PEER_ADDRESS_INVALID")
        if marker:
            sid=int(marker.group(1))
            if sid in managed:
                raise SystemExit("DUPLICATE_WG_MANAGED_PEER")
            managed[sid]=(part,addr.group(1) if addr else None)
        else:
            unmanaged.append(part)

    pool=(
        [f"10.93.0.{i}" for i in range(2,255)]
        + [str(ip) for ip in ipaddress.ip_network("10.96.0.0/21").hosts()
           if str(ip)!="10.96.0.1"]
    )
    allocated={}
    for sid in sorted(peers):
        old=managed.get(sid)
        old_address=old[1] if old else None
        if old_address:
            address=str(ipaddress.ip_interface(old_address).ip)
        else:
            address=next((candidate for candidate in pool if candidate not in taken),None)
            if not address:
                raise SystemExit("WG_PEER_ADDRESS_POOL_EXHAUSTED")
        if address in allocated.values():
            raise SystemExit("WG_PEER_ADDRESS_COLLISION")
        taken.add(address)
        allocated[sid]=address
    new_blocks=[]
    for sid in sorted(managed):
        if sid not in peers:
            new_blocks.append(managed[sid][0])
    for sid in sorted(peers):
        new_blocks.append(
            "[Peer]\n"
            +"# TwinPanel-central subscription="+str(sid)+"\n"
            +"PublicKey = "+peers[sid]+"\n"
            +"AllowedIPs = "+allocated[sid]+"/32\n"
        )
    new_text=base.rstrip()+"\n\n"+"".join(unmanaged)+"\n".join(new_blocks)
    if not new_text.endswith("\n"):
        new_text+="\n"
    if new_text==original:
        print(json.dumps({"ok":True,"applied":len(peers),
            "changed":False,"addresses":allocated}))
        raise SystemExit(0)
    backup_dir=CONF.parent/".twinpanel-central-wg-backups"
    backup_dir.mkdir(mode=0o700,exist_ok=True)
    os.chmod(backup_dir,0o700)
    backup=backup_dir/("pre-bulk-"+str(time.time_ns())+".conf")
    shutil.copy2(CONF,backup)
    os.chmod(backup,0o600)
    # wg-quick requires a .conf basename of at most 15 characters.
    # Long random stage/backup filenames make real wg-quick strip fail.
    fd,temp=tempfile.mkstemp(prefix="tpw-",suffix=".conf",dir=str(CONF.parent))
    stripped=None
    previous_strip=None
    previous_conf=None
    sync_attempted=False
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as out:
            out.write(new_text)
            out.flush()
            os.fsync(out.fileno())
        # The immutable backup has a long audit filename, so use a
        # short-name 0600 copy for wg-quick's strict config parser.
        pfd,previous_conf=tempfile.mkstemp(
            prefix="tpb-",suffix=".conf",dir=str(CONF.parent),
        )
        os.close(pfd)
        os.chmod(previous_conf,0o600)
        shutil.copyfile(backup,previous_conf)
        result=subprocess.run(["wg-quick","strip",temp],capture_output=True,
            text=True,timeout=20,check=False)
        previous=subprocess.run(["wg-quick","strip",previous_conf],
            capture_output=True,text=True,timeout=20,check=False)
        if result.returncode or previous.returncode:
            raise SystemExit("WG_STAGED_CONFIG_INVALID")
        with tempfile.NamedTemporaryFile(
            mode="w",encoding="utf-8",dir=str(CONF.parent),
            prefix=".central-wg-stripped-",delete=False,
        ) as handle:
            stripped=handle.name
            os.chmod(stripped,0o600)
            handle.write(result.stdout)
        with tempfile.NamedTemporaryFile(
            mode="w",encoding="utf-8",dir=str(CONF.parent),
            prefix=".central-wg-previous-",delete=False,
        ) as handle:
            previous_strip=handle.name
            os.chmod(previous_strip,0o600)
            handle.write(previous.stdout)
        sync_attempted=True
        synced=subprocess.run(["wg","syncconf",IFACE,stripped],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            timeout=40,check=False)
        if synced.returncode:
            raise RuntimeError("WG_LIVE_SYNC_FAILED")
        checked=subprocess.run(["wg","show",IFACE,"peers"],capture_output=True,
            text=True,timeout=15,check=False)
        if checked.returncode or not set(peers.values()).issubset(
            {x.strip() for x in checked.stdout.splitlines()}
        ):
            raise RuntimeError("WG_LIVE_PEER_VERIFICATION_FAILED")
        os.replace(temp,CONF)
    except BaseException:
        if sync_attempted and previous_strip:
            restored=subprocess.run(["wg","syncconf",IFACE,previous_strip],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                timeout=40,check=False)
            if restored.returncode:
                raise SystemExit("WG_LIVE_SYNC_ROLLBACK_FAILED")
        raise
    finally:
        for path in (temp,stripped,previous_strip,previous_conf):
            if path and os.path.exists(path):
                os.unlink(path)
print(json.dumps({"ok":True,"applied":len(peers),
                  "changed":True,"addresses":allocated}))
'''
    for marker,value in {
        "__CONF__":repr(config_path),
        "__IFACE__":repr(interface),
        "__LOCK__":repr(lock_path),
    }.items():
        src=src.replace(marker,value)
    return src


async def apply_bulk(conn:Any,peers:list[dict])->dict[str,Any]:
    if not 1<=len(peers)<=3000:
        raise ValueError("WireGuard batch must be 1..3000 peers")
    payload=base64.b64encode(remote_script().encode()).decode("ascii")
    proc=await asyncio.wait_for(
        conn.create_process("python3 -c \"$(printf '%s' '"+payload+"' | base64 -d)\""),
        timeout=30,
    )
    proc.stdin.write(json.dumps({"peers":peers}))
    proc.stdin.write_eof()
    result=await asyncio.wait_for(proc.wait(),timeout=200)
    if result.exit_status:
        raise RuntimeError("WG_REMOTE_BULK_FAILED")
    try:
        summary=json.loads((result.stdout or "").strip().splitlines()[-1])
    except (ValueError,IndexError):
        raise RuntimeError("WG_BULK_ACK_MISSING")
    if not summary.get("ok") or int(summary.get("applied") or 0)!=len(peers):
        raise RuntimeError("WG_BULK_ACK_MISMATCH")
    return summary
