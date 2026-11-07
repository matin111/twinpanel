"""One-SSH Cisco/OpenConnect account staging for one hidden, ready Exit.

Uses the EXISTING ocpasswd password-file contract. Runs the ocpasswd hashing
tool on a private temporary copy, then swaps the file atomically; ocserv
is never restarted. All account identity and entitlement comes from TwinPanel.
No users/credentials are displayed in logs or on the command line.

Default is dry-run; --apply requires exact --confirm-node-id.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.central_runtime_ownership_v1 import allow_central_node
from app.database import SessionLocal
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType,
    ProtocolCredential, Subscription, SubscriptionNode, SubscriptionProtocol,
    SubscriptionStatus,
)
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.services.central_family_readiness_v1 import verify_central_family_readiness
from scripts.twinpanel_central_l2tp_node_bulk_v1 import (
    account_rows, selected_subscriptions,
)

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
MAX_USERS = 3000


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=MAX_USERS)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-node-id", type=int)
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= MAX_USERS or args.node_id < 1:
        parser.error("invalid scope/limit")
    if args.apply and args.confirm_node_id != args.node_id:
        parser.error("--apply requires matching --confirm-node-id")
    return args


def cisco_merge_script(path: str = "/etc/ocserv/ocpasswd") -> str:
    # This script is sent to the node without any customer secrets.
    # JSON credentials are streamed exclusively on SSH stdin.
    return f'''import fcntl, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

TARGET=Path({path!r})
payload=json.load(sys.stdin)
users=payload.get("accounts")
if not isinstance(users,list) or not 0 < len(users) <= 3000:
    raise SystemExit("INVALID_CISCO_PAYLOAD")
seen=set()
for item in users:
    name=item.get("username")
    password=item.get("password")
    if not isinstance(name,str) or not isinstance(password,str):
        raise SystemExit("INVALID_CISCO_IDENTITY")
    if not name or not password or any(c in name+password for c in ("\\n","\\r","\\0")):
        raise SystemExit("INVALID_CISCO_IDENTITY")
    if name in seen:
        raise SystemExit("DUPLICATE_CISCO_ACCOUNT")
    seen.add(name)
if TARGET.is_symlink() or (TARGET.exists() and not TARGET.is_file()):
    raise SystemExit("CISCO_AUTH_FILE_UNSAFE")
TARGET.parent.mkdir(parents=True,exist_ok=True)
with open(TARGET.parent / ".twinpanel-central-cisco-bulk.lock","a+") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    backup_dir=TARGET.parent / ".twinpanel-central-cisco-backups"
    backup_dir.mkdir(mode=0o700,exist_ok=True)
    os.chmod(backup_dir,0o700)
    fd,tmp=tempfile.mkstemp(dir=str(TARGET.parent),prefix=".twinpanel-ocpasswd-bulk-")
    os.close(fd)
    try:
        if TARGET.exists():
            shutil.copy2(TARGET,tmp)
        os.chmod(tmp,0o600)
        # ocpasswd owns its hashing algorithm and file representation.
        # We never create hashes ourselves or restart a service.
        for item in users:
            result=subprocess.run(
                ["ocpasswd","-c",tmp,item["username"]],
                input=item["password"]+"\\n"+item["password"]+"\\n",
                text=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                timeout=15,check=False,
            )
            if result.returncode:
                raise SystemExit("CISCO_PASSWORD_HASH_FAILED")
        parsed=[s for s in Path(tmp).read_text(encoding="utf-8").splitlines()
                if s.strip() and not s.lstrip().startswith("#")]
        users_in_file={{s.split(":",1)[0] for s in parsed if ":" in s}}
        if not seen.issubset(users_in_file):
            raise SystemExit("CISCO_ACCOUNTS_MISSING_IN_STAGED_FILE")
        if TARGET.exists():
            backup=backup_dir / ("pre-bulk-"+str(time.time_ns())+".auth")
            shutil.copy2(TARGET,backup)
            os.chmod(backup,0o600)
        os.replace(tmp,TARGET)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
print(json.dumps({{"ok":True,"accounts":len(users),"verified":len(seen)}}))
'''


async def remote_stage(node: Node, db, accounts: list[dict]) -> dict:
    import base64
    conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=25)
    try:
        program = base64.b64encode(cisco_merge_script().encode()).decode()
        process = await asyncio.wait_for(
            conn.create_process(
                "python3 -c \"$(printf '%s' '" + program + "' | base64 -d)\""
            ), timeout=20,
        )
        process.stdin.write(json.dumps({"accounts": accounts}, ensure_ascii=False))
        process.stdin.write_eof()
        # ocpasswd hashes each account but there is no network per account.
        result = await asyncio.wait_for(process.wait(), timeout=700)
        if result.exit_status != 0:
            raise RuntimeError("CISCO_CENTRAL_STAGE_FAILED")
        summary = json.loads((result.stdout or "").strip().splitlines()[-1])
        if not summary.get("ok") or int(summary.get("verified") or 0) != len(accounts):
            raise RuntimeError("CISCO_CENTRAL_STAGE_UNCONFIRMED")
        return summary
    finally:
        conn.close()
        await conn.wait_closed()


async def run(node_id: int, limit: int, apply: bool) -> None:
    with SessionLocal() as db:
        node = db.get(Node, node_id)
        if (
            node is None or node.node_type != NodeType.EXIT
            or node.retired_at is not None or node.status != NodeStatus.ONLINE
            or not allow_central_node(db,node) or not bool(node.enable_cisco)
        ):
            raise RuntimeError("REQUIRES_HIDDEN_READY_EXIT")
        cfg = db.query(NodeProtocolConfig).filter_by(
            node_id=node_id, protocol="cisco",
        ).one_or_none()
        if cfg is None or str(getattr(cfg.status, "value", cfg.status)).lower() != "online":
            raise RuntimeError("CISCO_NODE_PROTOCOL_NOT_READY")
        subscriptions = selected_subscriptions(db, node_id, limit, "cisco")
        rows = account_rows(subscriptions)
        print("CENTRAL_CISCO_PLAN", json.dumps({
            "node_id": node_id, "selected": len(rows),
            "write_enabled": apply, "model": "one_ssh_one_db_commit",
        }), flush=True)
        if not apply or not rows:
            return
        readiness = await asyncio.wait_for(
            verify_central_family_readiness(db, node_id, {"cisco"}), timeout=510,
        )
        if not readiness.get("ok"):
            raise RuntimeError("16_PROTOCOL_READINESS_FAILED")

        confirmed = await remote_stage(node, db, rows)
        db.expire_all()
        valid = {int(s.id) for s in selected_subscriptions(db, node_id, MAX_USERS, "cisco")}
        if not {int(r["id"]) for r in rows}.issubset(valid):
            raise RuntimeError("ELIGIBILITY_CHANGED_DURING_CISCO_STAGE")
        node = db.get(Node, node_id)
        if not node or not allow_central_node(db,node):
            raise RuntimeError("CISCO_NODE_VISIBILITY_CHANGED")
        host, port = ad._tunnel_access_endpoint(db, node, "cisco")
        creds = {
            int(c.subscription_id): c for c in db.query(ProtocolCredential)
            .filter(
                ProtocolCredential.subscription_id.in_([int(r["id"]) for r in rows]),
                ProtocolCredential.protocol=="cisco",
            ).with_for_update().all()
        }
        written=0
        for row in rows:
            sid=int(row["id"])
            credential=creds.get(sid)
            if credential is None:
                credential=ProtocolCredential(subscription_id=sid, protocol="cisco")
                db.add(credential)
            items=ad._autosync_credential_items(credential)
            if any(ad._autosync_item_node_id(x)==node_id for x in items):
                continue
            items.append({
                "node_id":node_id, "node":node.name, "server":host,
                "server_ip":host, "port":port,
                "username":row["username"],"password":row["password"],
            })
            credential.username=row["username"]
            credential.secret_encrypted=ad._enc({"password":row["password"]})
            credential.config_text_encrypted=ad._enc(items)
            credential.is_active=True
            written+=1
        db.commit()
        print("CENTRAL_CISCO_RESULT",json.dumps({
            "node_id":node_id,"selected":len(rows),
            "remote_accounts":confirmed["accounts"],
            "centrally_saved":written,"node_remains_hidden":True,
        }),flush=True)


if __name__=="__main__":
    args=parse_args()
    try:
        asyncio.run(run(args.node_id,args.limit,args.apply))
    except Exception as exc:
        print("CENTRAL_CISCO_SAFE_STOP",{
            "node_id":args.node_id,"error_type":type(exc).__name__,
        },flush=True)
        raise SystemExit(2)
