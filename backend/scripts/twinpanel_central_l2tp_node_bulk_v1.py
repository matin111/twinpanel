"""Stage L2TP on ONE hidden Exit with a single SSH session and one DB commit.

The per-account /_l2tp SSH loop is intentionally not used. This first
centralized adapter is independent of V2Ray, WireGuard, and sing-box.

Default read-only. Apply requires matching node-id confirmation. Never
publish the node, create memberships or bypass purchased entitlements.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)
from app.mother_access import get_or_create_l2tp_psk
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.services.new_node_readiness_v1 import verify_new_exit_readiness

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)

MAX_USERS = 3000
USERNAME = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")


def args_parser(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=MAX_USERS)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm-node-id", type=int)
    args = p.parse_args(argv)
    if args.node_id < 1 or not 1 <= args.limit <= MAX_USERS:
        p.error("node-id must be positive and limit 1..3000")
    if args.apply and args.confirm_node_id != args.node_id:
        p.error("--apply requires --confirm-node-id matching node-id")
    return args


def selected_subscriptions(db, node_id: int, limit: int, protocol: str = "l2tp") -> list[Subscription]:
    now = datetime.utcnow()
    return (
        db.query(Subscription)
        .join(SubscriptionNode, SubscriptionNode.subscription_id == Subscription.id)
        .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id == Subscription.id)
        .filter(
            SubscriptionNode.node_id == int(node_id),
            SubscriptionProtocol.protocol == protocol,
            Subscription.status == SubscriptionStatus.ACTIVE,
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
            or_(
                Subscription.traffic_limit_bytes <= 0,
                Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes,
            ),
        )
        .distinct()
        .order_by(Subscription.id.asc())
        .limit(limit)
        .all()
    )


def account_rows(subs) -> list[dict]:
    rows = []
    usernames = set()
    for sub in subs:
        name = str(sub.account_username or "")
        password = str(sub.account_password_encrypted or "")
        if not USERNAME.fullmatch(name) or not password or any(
            char in password for char in ("\n", "\r", "\x00")
        ):
            raise RuntimeError("ELIGIBLE_ACCOUNT_WITH_INVALID_IDENTITY")
        if name in usernames:
            raise RuntimeError("DUPLICATE_CENTRAL_ACCOUNT_USERNAME")
        usernames.add(name)
        rows.append({"id": int(sub.id), "username": name, "password": password})
    return rows


def remote_merge_source(path: str = "/etc/ppp/chap-secrets") -> str:
    """Remote Python has no secrets in argv: account JSON arrives on stdin.

    Preserves nonmatching/manual rows. Only the specified users are
    overwritten; never strips a different user's access. No service restart.
    """
    return f'''import fcntl, json, os, shlex, shutil, stat, sys, tempfile, time
from pathlib import Path
TARGET=Path({path!r})
doc=json.load(sys.stdin)
accounts=doc.get("accounts")
if not isinstance(accounts,list) or not 0 < len(accounts) <= 3000:
    raise SystemExit("INVALID_CENTRAL_ACCOUNT_PAYLOAD")
names=set()
for row in accounts:
    name=row.get("username")
    pwd=row.get("password")
    if not isinstance(name,str) or not isinstance(pwd,str) or not name or not pwd:
        raise SystemExit("INVALID_CENTRAL_ACCOUNT_IDENTITY")
    if any(x in name+pwd for x in ("\\n","\\r","\\0")) or name in names:
        raise SystemExit("INVALID_CENTRAL_ACCOUNT_DUPLICATE_OR_NEWLINE")
    names.add(name)
if TARGET.is_symlink() or (TARGET.exists() and not TARGET.is_file()):
    raise SystemExit("L2TP_SECRET_FILE_NOT_REGULAR")
TARGET.parent.mkdir(parents=True,exist_ok=True)
lockpath=TARGET.parent / ".twinpanel-central-l2tp-bulk.lock"
lock=open(lockpath,"a+",encoding="utf-8")
fcntl.flock(lock,fcntl.LOCK_EX)
previous=TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
kept=[]
for line in previous.splitlines(keepends=True):
    stripped=line.strip()
    if not stripped or stripped.startswith("#"):
        kept.append(line)
        continue
    try:
        fields=shlex.split(line,comments=True)
    except ValueError:
        kept.append(line)
        continue
    if not fields or fields[0] not in names:
        kept.append(line)
out="".join(kept)
if out and not out.endswith("\\n"):
    out+="\\n"
def ppp_field(value):
    return '"' + value.replace("\\\\","\\\\\\\\").replace('"','\\\\"') + '"'
for row in accounts:
    out+=ppp_field(row["username"])+" * "+ppp_field(row["password"])+" * # TwinPanel-central\\n"
if out == previous:
    print(json.dumps({{"ok":True,"accounts":len(accounts),"changed":False}}))
    raise SystemExit(0)
backups=TARGET.parent / ".twinpanel-central-l2tp-backups"
backups.mkdir(mode=0o700,exist_ok=True)
os.chmod(backups,0o700)
if TARGET.exists():
    backup=backups / ("pre-bulk-"+str(time.time_ns())+".secrets")
    shutil.copy2(TARGET,backup)
    os.chmod(backup,0o600)
fd,tmp=tempfile.mkstemp(prefix=".twinpanel-chap-bulk-",dir=str(TARGET.parent))
try:
    os.fchmod(fd,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as stream:
        stream.write(out)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp,TARGET)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print(json.dumps({{"ok":True,"accounts":len(accounts),"changed":True}}))
'''


async def apply_remote(node: Node, db, rows: list[dict]) -> dict:
    conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=25)
    try:
        src = remote_merge_source()
        # Source is static and holds no credentials. Secrets travel only on
        # the SSH stdin stream (not command-line arguments or journal).
        import base64
        encoded = base64.b64encode(src.encode()).decode("ascii")
        cmd = "python3 -c \"$(printf '%s' '" + encoded + "' | base64 -d)\""
        proc = await asyncio.wait_for(conn.create_process(cmd), timeout=20)
        proc.stdin.write(json.dumps({"accounts": rows}, ensure_ascii=False))
        proc.stdin.write_eof()
        result = await asyncio.wait_for(proc.wait(), timeout=100)
        if result.exit_status != 0:
            raise RuntimeError("L2TP_REMOTE_MERGE_FAILED")
        # stdout contains counts/booleans only; never print remote stderr.
        outcome = json.loads((result.stdout or "").strip().splitlines()[-1])
        if not outcome.get("ok") or int(outcome.get("accounts") or 0) != len(rows):
            raise RuntimeError("L2TP_REMOTE_MERGE_UNCONFIRMED")
        return outcome
    finally:
        conn.close()
        await conn.wait_closed()


async def run(node_id: int, limit: int, apply: bool) -> None:
    with SessionLocal() as db:
        node = db.get(Node, int(node_id))
        if (
            node is None or node.node_type != NodeType.EXIT
            or node.retired_at is not None or node.status != NodeStatus.ONLINE
            or bool(node.show_to_users) or not bool(node.enable_l2tp)
        ):
            raise RuntimeError("REQUIRES_HIDDEN_ONLINE_PREPARED_EXIT")
        cfg = db.query(NodeProtocolConfig).filter_by(
            node_id=int(node_id), protocol="l2tp",
        ).one_or_none()
        if cfg is None or str(getattr(cfg.status, "value", cfg.status)).lower() != "online":
            raise RuntimeError("L2TP_PROTOCOL_NOT_READY")
        subs = selected_subscriptions(db, node_id, limit)
        rows = account_rows(subs)
        print("CENTRAL_L2TP_PLAN", json.dumps({
            "node_id": node_id, "selected": len(rows),
            "write_enabled": bool(apply), "mode": "single_ssh_one_db_commit",
        }), flush=True)
        if not apply or not rows:
            return
        readiness = await asyncio.wait_for(
            verify_new_exit_readiness(db, node_id), timeout=510,
        )
        if not readiness.get("ok"):
            raise RuntimeError("16_PROTOCOL_READINESS_NOT_VERIFIED")
        result = await apply_remote(node, db, rows)
        # If central DB commit fails after the remote auth file is updated,
        # rerunning is safe: remote file will be idempotent and the node remains
        # hidden. No partially published subscription can be delivered.
        db.expire_all()
        now = datetime.utcnow()
        user_ids = {int(s.id) for s in subs}
        live = {int(s.id): s for s in selected_subscriptions(db, node_id, MAX_USERS)}
        if not user_ids.issubset(live):
            raise RuntimeError("ELIGIBILITY_CHANGED_AFTER_REMOTE_MERGE")
        psk = get_or_create_l2tp_psk(db)
        node = db.get(Node, node_id)
        host = ad._l2tp_tunnel_access_host(db, node)
        existing = {
            int(c.subscription_id): c for c in (
                db.query(ProtocolCredential)
                .filter(ProtocolCredential.subscription_id.in_(list(user_ids)),
                        ProtocolCredential.protocol == "l2tp")
                .with_for_update()
                .all()
            )
        }
        stored = 0
        for row in rows:
            sid = int(row["id"])
            cred = existing.get(sid)
            if cred is None:
                cred = ProtocolCredential(subscription_id=sid, protocol="l2tp")
                db.add(cred)
            items = ad._autosync_credential_items(cred)
            if any(ad._autosync_item_node_id(item) == node_id for item in items):
                continue
            item = {
                "node_id": node_id, "node": node.name,
                "server": host, "server_ip": host, "ports": "500/4500 UDP",
                "username": row["username"], "password": row["password"],
                "psk": psk,
            }
            items.append(item)
            cred.username = row["username"]
            cred.secret_encrypted = ad._enc({"password": row["password"]})
            cred.config_text_encrypted = ad._enc(items)
            cred.is_active = True
            stored += 1
        db.commit()
        print("CENTRAL_L2TP_RESULT", json.dumps({
            "node_id": node_id, "selected": len(rows),
            "server_authenticated_accounts": int(result["accounts"]),
            "centrally_saved_node_credentials": stored,
            "node_remains_hidden": True,
        }), flush=True)


if __name__ == "__main__":
    args = args_parser()
    try:
        asyncio.run(run(args.node_id, args.limit, args.apply))
    except Exception as exc:
        print("CENTRAL_L2TP_SAFE_STOP", {
            "node_id": args.node_id, "error_type": type(exc).__name__,
        }, flush=True)
        raise SystemExit(2)
