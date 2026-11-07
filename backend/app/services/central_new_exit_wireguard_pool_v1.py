"""Prepare an unused hidden Exit WireGuard listener for central bulk peers.

Requires an already installed wg-access0 with NO peers; never resets an
existing client's WireGuard session. Maintains the original 10.93/24 subnet,
adds central 10.96/21 pool live without a wg-quick restart, persists its
Address and egress NAT for future boot, and rolls back on a failed preflight.
"""
from __future__ import annotations

import asyncio
import base64
import json
import shlex

_REMOTE = r'''
import fcntl
import ipaddress
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

CONF=pathlib.Path("/etc/wireguard/wg-access0.conf")
IFACE="wg-access0"
OLD="10.93.0.1/24"
NEW="10.96.0.1/21"
NETS=("10.93.0.0/24","10.96.0.0/21")
LOCK=pathlib.Path("/run/twinpanel-wg-allocation.lock")

def run(args,timeout=9):
    return subprocess.run(
        args,capture_output=True,text=True,check=False,timeout=timeout,
    )
def must(args,reason):
    result=run(args)
    if result.returncode:
        raise RuntimeError(reason)
    return result.stdout
def check_nat(network,dev):
    return run([
        "iptables","-t","nat","-C","POSTROUTING",
        "-s",network,"-o",dev,"-j","MASQUERADE",
    ]).returncode==0

if CONF.is_symlink() or not CONF.is_file():
    raise RuntimeError("WG_CENTRAL_POOL_INVALID_CONFIG")
LOCK.parent.mkdir(parents=True,exist_ok=True)
with open(LOCK,"a+") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    original=CONF.read_text(encoding="utf-8")
    addr=re.findall(r"(?mi)^\\s*Address\\s*=\\s*([^\\n]+)",original)
    if len(addr)!=1:
        raise RuntimeError("WG_CENTRAL_POOL_ADDRESS_AMBIGUOUS")
    currently={str(x.strip()) for x in addr[0].split(",")}
    if OLD not in currently or not currently.issubset({OLD,NEW}):
        raise RuntimeError("WG_CENTRAL_POOL_UNEXPECTED_ADDRESS")
    if re.search(r"(?mi)^\\s*(PostUp|PostDown)\\s*=",original):
        raise RuntimeError("WG_CENTRAL_POOL_UNMANAGED_NAT_RULES")
    if re.search(r"(?mi)^\\s*SaveConfig\\s*=\\s*true\\b",original):
        raise RuntimeError("WG_CENTRAL_POOL_SAVECONFIG_UNSAFE")
    if not original.lstrip().startswith("[Interface]"):
        raise RuntimeError("WG_CENTRAL_POOL_INVALID_INTERFACE")
    peers=must(["wg","show",IFACE,"peers"],"WG_CENTRAL_POOL_INTERFACE_OFFLINE")
    if peers.strip() or "[Peer]" in original:
        raise RuntimeError("WG_CENTRAL_POOL_EXISTING_PEERS")
    live=must(["ip","-4","-o","addr","show",IFACE],
              "WG_CENTRAL_POOL_INTERFACE_MISSING")
    if OLD not in live:
        raise RuntimeError("WG_CENTRAL_POOL_BASE_ADDRESS_NOT_LIVE")
    route=must(["ip","-4","route","show","default"],
               "WG_CENTRAL_POOL_NO_PUBLIC_EGRESS")
    match=re.search(r"\\bdev\\s+([a-zA-Z0-9_.-]+)",route)
    if not match:
        raise RuntimeError("WG_CENTRAL_POOL_NO_EGRESS_INTERFACE")
    public_dev=match.group(1)
    already_live=NEW in live
    if not already_live:
        conflict=must(["ip","-4","route","show","10.96.0.0/21"],
                      "WG_CENTRAL_POOL_ROUTE_CHECK_FAILED")
        if conflict.strip():
            raise RuntimeError("WG_CENTRAL_POOL_ROUTE_CONFLICT")

    new_address=OLD+", "+NEW
    updated=re.sub(
        r"(?mi)^(\\s*Address\\s*=\\s*)[^\\n]+",
        lambda m:m.group(1)+new_address,
        original,count=1,
    )
    rules=[]
    for net in NETS:
        rules.append((
            "iptables -t nat -A POSTROUTING -s "+net+
            " -o "+public_dev+" -j MASQUERADE",
            "iptables -t nat -D POSTROUTING -s "+net+
            " -o "+public_dev+" -j MASQUERADE",
        ))
    additions="".join(
        "PostUp = "+up+"\\nPostDown = "+down+"\\n"
        for up,down in rules
    )
    # Insert directives INSIDE [Interface], not after [Peer].
    begin=updated.find("\\n[Peer]")
    if begin<0:begin=len(updated)
    updated=updated[:begin].rstrip()+"\\n"+additions+updated[begin:]
    backup=CONF.with_suffix(".central-pool-preinstall.bak")
    if not backup.exists():
        shutil.copy2(CONF,backup)
        os.chmod(backup,0o600)
    fd,tmp=tempfile.mkstemp(prefix=".tp-central-pool-",dir=str(CONF.parent))
    added_ip=False
    added_nat=[]
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as out:
            out.write(updated)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp,0o600)
        # wg-quick strip validates Interface-only metadata without restarting.
        checked=run(["wg-quick","strip",tmp],timeout=12)
        if checked.returncode:
            raise RuntimeError("WG_CENTRAL_POOL_CONFIG_INVALID")
        if not already_live:
            must(["ip","address","add",NEW,"dev",IFACE],
                 "WG_CENTRAL_POOL_ADDRESS_ADD_FAILED")
            added_ip=True
        for network in NETS:
            if not check_nat(network,public_dev):
                must([
                    "iptables","-t","nat","-A","POSTROUTING",
                    "-s",network,"-o",public_dev,"-j","MASQUERADE",
                ],"WG_CENTRAL_POOL_NAT_FAILED")
                added_nat.append(network)
        os.replace(tmp,CONF)
        # Only boolean metadata: NEVER log private keys or remote files.
        print(json.dumps({"ok":True,"pool":"10.96/21","nat_rules":len(NETS),
                          "restarted":False,"existing_peers":0}))
    except BaseException:
        for network in reversed(added_nat):
            run([
                "iptables","-t","nat","-D","POSTROUTING",
                "-s",network,"-o",public_dev,"-j","MASQUERADE",
            ])
        if added_ip:run(["ip","address","del",NEW,"dev",IFACE])
        raise
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
'''


async def prepare_hidden_exit_wireguard_pool(conn) -> dict:
    """Run once before central bulk on a still-unused, hidden Exit."""
    payload=base64.b64encode(_REMOTE.encode("utf-8")).decode("ascii")
    command='python3 -c "$(printf %s '+shlex.quote(payload)+' | base64 -d)"'
    result=await asyncio.wait_for(
        conn.run(command,check=False,timeout=35),timeout=40,
    )
    if result.exit_status != 0:
        # Remote errors may contain environment or installation details.
        raise RuntimeError("CENTRAL_WG_POOL_PREPARATION_FAILED")
    try:
        summary=json.loads((result.stdout or "").strip().splitlines()[-1])
    except (IndexError,ValueError) as exc:
        raise RuntimeError("CENTRAL_WG_POOL_ACK_MISSING") from exc
    if (summary.get("ok") is not True or
            summary.get("pool")!="10.96/21" or
            summary.get("existing_peers")!=0):
        raise RuntimeError("CENTRAL_WG_POOL_ACK_INVALID")
    return summary
