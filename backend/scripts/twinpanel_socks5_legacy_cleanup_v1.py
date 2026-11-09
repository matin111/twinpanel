"""Revoke obsolete ACTIVE subscription SOCKS5 logins after verified cutover.

Only removes tp-sub-<subscription-id> when the new canonical account login
exists on that same online Exit. Does not affect expired users, other
protocols, subscription secrets, billing, or active tunnel routes.
Dry run by default. Exactly one atomic sing-box restart per affected node.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import shlex
import sys
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.database import SessionLocal
from app.models import Node, NodeStatus, ProtocolCredential, Subscription, SubscriptionStatus
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.singbox_subscription_accounts import read_inbound

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)

REMOTE = r'''import fcntl
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CONFIG=Path("/etc/twinpanel/sing-box/config.json")
SERVICE="twinpanel-sing-box.service"
BINARY="/usr/local/bin/twinpanel-sing-box"
LOCK=Path("/run/twinpanel-singbox-batch.lock")
PAIRS=json.loads(__PAIRS__)

LOCK.parent.mkdir(parents=True,exist_ok=True)
with open(LOCK,"a+") as guard:
    fcntl.flock(guard,fcntl.LOCK_EX)
    if CONFIG.is_symlink() or not CONFIG.is_file():
        raise SystemExit("SOCKS5_CONFIG_UNSAFE")
    original=CONFIG.read_text(encoding="utf-8")
    config=json.loads(original)
    inbounds=[
        x for x in config.get("inbounds",[])
        if isinstance(x,dict) and x.get("type")=="socks"
        and x.get("tag")=="twinpanel-socks5-in"
    ]
    if len(inbounds)!=1:
        raise SystemExit("SOCKS5_INBOUND_NOT_UNIQUE")
    inbound=inbounds[0]
    users=inbound.get("users")
    if not isinstance(users,list):
        raise SystemExit("SOCKS5_USERS_NOT_LIST")
    by_name={
        x.get("username"):x for x in users
        if isinstance(x,dict) and isinstance(x.get("username"),str)
    }
    old_to_remove=set()
    for old,new in PAIRS:
        if old==new:
            continue
        if old in by_name:
            if new not in by_name:
                raise SystemExit("SOCKS5_CANONICAL_CREDENTIAL_MISSING")
            old_to_remove.add(old)
    if not old_to_remove:
        print(json.dumps({"ok":True,"removed":0,"restarted":False}))
        raise SystemExit(0)
    inbound["users"]=[
        x for x in users if not (
            isinstance(x,dict) and x.get("username") in old_to_remove
        )
    ]
    fd,tmp=tempfile.mkstemp(prefix=".socks5-cleanup-",dir=str(CONFIG.parent))
    os.fchmod(fd,0o600)
    backup=CONFIG.with_name(CONFIG.name+".pre-socks5-cleanup")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as dst:
            json.dump(config,dst,ensure_ascii=False,indent=2)
            dst.write("\n")
            dst.flush()
            os.fsync(dst.fileno())
        if subprocess.run([BINARY,"check","-c",tmp],timeout=120,
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode:
            raise SystemExit("SOCKS5_CLEANUP_CONFIG_INVALID")
        shutil.copy2(CONFIG,backup)
        os.chmod(backup,0o600)
        os.replace(tmp,CONFIG)
        if subprocess.run(["systemctl","restart",SERVICE],timeout=70,
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode:
            shutil.copy2(backup,CONFIG)
            subprocess.run(["systemctl","restart",SERVICE],timeout=70,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            raise SystemExit("SOCKS5_CLEANUP_RESTART_ROLLED_BACK")
        if subprocess.run(["systemctl","is-active","--quiet",SERVICE],
                          timeout=10).returncode:
            shutil.copy2(backup,CONFIG)
            subprocess.run(["systemctl","restart",SERVICE],timeout=70,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            raise SystemExit("SOCKS5_CLEANUP_UNHEALTHY_ROLLED_BACK")
        print(json.dumps({"ok":True,"removed":len(old_to_remove),
                          "restarted":True}))
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
        # Keep the root-only local rollback snapshot; management backup
        # retention can remove it on the next successful deployment.
'''


def _eligible(sub: Subscription) -> bool:
    now=datetime.utcnow()
    return (
        sub.status==SubscriptionStatus.ACTIVE
        and (sub.expires_at is None or sub.expires_at>now)
        and (not sub.traffic_limit_bytes
             or sub.traffic_used_bytes<sub.traffic_limit_bytes)
    )


async def run():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id",type=int,action="append",required=True)
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--confirm",choices=["SOCKS5"],default=None)
    options=parser.parse_args()
    if options.apply and options.confirm!="SOCKS5":
        raise RuntimeError("EXPLICIT_CONFIRMATION_REQUIRED")
    with SessionLocal() as db:
        for nid in sorted(set(options.node_id)):
            node=db.get(Node,nid)
            if (
                node is None or node.retired_at is not None
                or node.status != NodeStatus.ONLINE
            ):
                raise RuntimeError("SOCKS5_EXIT_NOT_ONLINE")
            pairs=[]
            for cred,sub in db.query(ProtocolCredential,Subscription).join(
                Subscription,Subscription.id==ProtocolCredential.subscription_id
            ).filter(ProtocolCredential.protocol=="socks5"):
                if not _eligible(sub):
                    continue
                value=ad._dec(cred.secret_encrypted)
                if not isinstance(value,dict):
                    raise RuntimeError("SOCKS5_CREDENTIAL_UNREADABLE")
                if (
                    value.get("username")!=str(sub.account_username or "")
                    or value.get("password")!=str(sub.account_password_encrypted or "")
                ):
                    raise RuntimeError("SOCKS5_CREDENTIAL_NOT_MIGRATED")
                if any(ad._autosync_item_node_id(i)==nid
                       for i in ad._autosync_credential_items(cred)):
                    pairs.append((f"tp-sub-{int(sub.id)}",str(sub.account_username)))
            conn=await asyncio.wait_for(
                connect_protocol_runtime(node,db),timeout=25
            )
            try:
                before=await read_inbound(conn,"socks5")
                usernames={
                    str(x.get("username") or "")
                    for x in before.get("users",[]) if isinstance(x,dict)
                }
                proposed=[(old,new) for old,new in pairs if old in usernames]
                if any(new not in usernames for _,new in proposed):
                    raise RuntimeError("SOCKS5_NEW_LOGIN_MISSING")
                print("SOCKS5_LEGACY_CLEANUP_PLAN",{
                    "node_id":nid,"active_old_logins":len(proposed),
                    "write_enabled":options.apply,
                },flush=True)
                if not options.apply or not proposed:
                    continue
                source=REMOTE.replace("__PAIRS__",repr(
                    json.dumps(proposed,ensure_ascii=False)))
                encoded=base64.b64encode(source.encode()).decode()
                command=(
                    "printf '%s' "+shlex.quote(encoded)
                    +" | base64 -d | python3"
                )
                response=await asyncio.wait_for(
                    conn.run(command,check=False),timeout=230
                )
                if response.exit_status:
                    # Never leak configs or credentials.
                    raise RuntimeError("SOCKS5_REMOTE_CLEANUP_FAILED")
                result=json.loads((response.stdout or "").strip().splitlines()[-1])
                if not result.get("ok"):
                    raise RuntimeError("SOCKS5_CLEANUP_RESULT_INVALID")
                after=await read_inbound(conn,"socks5")
                names={str(x.get("username") or "") for x in after.get("users",[])}
                if any(old in names or new not in names for old,new in proposed):
                    raise RuntimeError("SOCKS5_CLEANUP_VERIFICATION_FAILED")
                print("SOCKS5_LEGACY_CLEANUP_COMPLETE",{
                    "node_id":nid,"removed":result.get("removed"),
                    "canonical_logins_preserved":True,
                },flush=True)
            finally:
                conn.close()
                await conn.wait_closed()


if __name__=="__main__":
    asyncio.run(run())
