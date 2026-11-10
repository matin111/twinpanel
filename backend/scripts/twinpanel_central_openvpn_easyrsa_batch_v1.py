"""One-SSH, bounded EasyRSA PKI materialization for ONE hidden Exit.

Unlike the central-CA-only adapter, this preserves this node's existing
EasyRSA issuer, client verification policy, and certificate revocation index.
Certificate issuance runs locally on the node (not one SSH per account);
clients retain individually revocable node-specific certificates.
No global PKI switch, service restart, or change to other Exit nodes.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy import or_

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.database import SessionLocal
from app.models import (
    Node,NodeProtocolConfig,NodeStatus,NodeType,ProtocolCredential,
    Subscription,SubscriptionNode,SubscriptionProtocol,SubscriptionStatus,
)
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import account_delivery as ad
from app.services.new_node_readiness_v1 import verify_new_exit_readiness

logging.getLogger("asyncssh").setLevel(logging.CRITICAL)
MAX_BATCH=140


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node-id",type=int,required=True)
    p.add_argument("--limit",type=int,default=100)
    p.add_argument("--all",action="store_true")
    p.add_argument("--apply",action="store_true")
    p.add_argument("--confirm-node-id",type=int)
    a=p.parse_args(argv)
    if a.node_id<1 or not 1<=a.limit<=MAX_BATCH:
        p.error("invalid node-id or limit 1..140")
    if a.apply and a.confirm_node_id!=a.node_id:
        p.error("--apply needs exact --confirm-node-id")
    return a


def remote_script(root="/etc/openvpn/easy-rsa")->str:
    src=r'''import json
import os
import re
import subprocess
import sys
from pathlib import Path
EASYRSA=Path(__ROOT__)
doc=json.load(sys.stdin)
node_id=doc.get("node_id")
ids=doc.get("ids")
if not isinstance(node_id,int) or node_id<1 or not isinstance(ids,list):
    raise SystemExit("INVALID_CERTIFICATE_SCOPE")
if not 0<len(ids)<=140 or len(set(ids))!=len(ids) or any(
    not isinstance(sid,int) or sid<1 for sid in ids
):
    raise SystemExit("INVALID_CERTIFICATE_IDENTITIES")
if not (EASYRSA/"easyrsa").is_file() or not (EASYRSA/"pki/ca.crt").is_file():
    raise SystemExit("OPENVPN_CA_NOT_INSTALLED")
if not (EASYRSA/"pki/private/ca.key").is_file():
    raise SystemExit("OPENVPN_CA_KEY_NOT_INSTALLED")
ca=(EASYRSA/"pki/ca.crt").read_text(encoding="utf-8")
if not ca.startswith("-----BEGIN CERTIFICATE-----"):
    raise SystemExit("OPENVPN_CA_INVALID")
results=[]
for sid in ids:
    cn="mv"+str(sid)+"n"+str(node_id)
    cert=EASYRSA/"pki/issued"/(cn+".crt")
    key=EASYRSA/"pki/private"/(cn+".key")
    if cert.exists()!=key.exists():
        raise SystemExit("OPENVPN_PARTIAL_EXISTING_IDENTITY")
    if not cert.exists():
        proc=subprocess.run(
            ["./easyrsa","build-client-full",cn,"nopass"],
            cwd=EASYRSA,env={**os.environ,"EASYRSA_BATCH":"1"},
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            timeout=75,check=False,
        )
        if proc.returncode:
            raise SystemExit("OPENVPN_EASYRSA_ISSUE_FAILED")
    verify=subprocess.run([
        "openssl","verify","-CAfile",str(EASYRSA/"pki/ca.crt"),str(cert),
    ],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        timeout=20,check=False)
    if verify.returncode:
        raise SystemExit("OPENVPN_CLIENT_CERT_VERIFICATION_FAILED")
    matches=re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                       cert.read_text(encoding="utf-8"),flags=re.S)
    if not matches:
        raise SystemExit("OPENVPN_PEM_CLIENT_CERT_MISSING")
    private=key.read_text(encoding="utf-8")
    if "PRIVATE KEY-----" not in private:
        raise SystemExit("OPENVPN_CLIENT_PRIVATE_KEY_MISSING")
    results.append({"id":sid,"certificate":matches[-1]+"\n","private_key":private})
# This is a secret-bearing reply; the controller MUST NEVER log stdout.
print(json.dumps({"ok":True,"ca":ca,"results":results},separators=(",",":")))
'''
    return src.replace("__ROOT__",repr(root))


def missing(db,node_id:int,limit:int):
    now=datetime.utcnow()
    subs=(db.query(Subscription)
      .join(SubscriptionNode,SubscriptionNode.subscription_id==Subscription.id)
      .join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id)
      .filter(SubscriptionNode.node_id==node_id,SubscriptionProtocol.protocol=="openvpn",
        Subscription.status==SubscriptionStatus.ACTIVE,
        or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
        or_(Subscription.traffic_limit_bytes<=0,
            Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes))
      .distinct().order_by(Subscription.id.asc()).all())
    creds={int(c.subscription_id):c for c in db.query(ProtocolCredential).filter(
        ProtocolCredential.protocol=="openvpn",
        ProtocolCredential.subscription_id.in_([int(s.id) for s in subs])).all()} if subs else {}
    pending=[]
    for sub in subs:
        cred=creds.get(int(sub.id))
        if cred is not None and cred.config_text_encrypted and not ad._autosync_credential_items(cred):
            raise RuntimeError("EXISTING_OPENVPN_CREDENTIAL_UNREADABLE")
        if not any(ad._autosync_item_node_id(item)==node_id
                   for item in ad._autosync_credential_items(cred)):
            pending.append(sub)
        if len(pending)>=limit:break
    return pending


async def one_cycle(db,node_id:int,limit:int,apply:bool):
    node=db.get(Node,node_id)
    if (node is None or node.node_type!=NodeType.EXIT or node.retired_at is not None
        or node.status!=NodeStatus.ONLINE or node.show_to_users or not node.enable_openvpn):
        raise RuntimeError("REQUIRES_HIDDEN_PREPARED_OPENVPN_EXIT")
    cfg=db.query(NodeProtocolConfig).filter_by(node_id=node_id,protocol="openvpn").first()
    if cfg is None or str(getattr(cfg.status,"value",cfg.status)).lower()!="online":
        raise RuntimeError("OPENVPN_NODE_LISTENER_NOT_REGISTERED")
    selected=missing(db,node_id,limit)
    print("CENTRAL_EASYRSA_OPENVPN_PLAN",json.dumps({
        "node_id":node_id,"selected":len(selected),"write_enabled":bool(apply),
        "remote_ssh_connections":1 if selected else 0,
    }),flush=True)
    if not selected or not apply:
        return 0
    program=base64.b64encode(remote_script().encode()).decode("ascii")
    conn=await asyncio.wait_for(connect_protocol_runtime(node,db),timeout=30)
    try:
        process=await asyncio.wait_for(
            conn.create_process("python3 -c \"$(printf '%s' '"+program+"' | base64 -d)\""),
            timeout=25,
        )
        process.stdin.write(json.dumps({
            "node_id":node_id,"ids":[int(s.id) for s in selected],
        }))
        process.stdin.write_eof()
        response=await asyncio.wait_for(process.wait(),timeout=1250)
        # stdout contains PEM private keys. Never include any remote
        # output in error messages or journal.
        if response.exit_status:
            raise RuntimeError("EASYRSA_REMOTE_STAGE_FAILED")
        try:
            outcome=json.loads((response.stdout or "").strip().splitlines()[-1])
        except (IndexError,ValueError):
            raise RuntimeError("EASYRSA_RESPONSE_INVALID")
        if not outcome.get("ok") or len(outcome.get("results") or [])!=len(selected):
            raise RuntimeError("EASYRSA_RESPONSE_INCOMPLETE")
    finally:
        conn.close();await conn.wait_closed()
    by_id={int(row["id"]):row for row in outcome["results"]}
    expected={int(s.id) for s in selected}
    if set(by_id)!=expected:
        raise RuntimeError("EASYRSA_CLIENT_SCOPE_MISMATCH")
    db.expire_all()
    now=datetime.utcnow()
    active_ids={int(s.id) for s in db.query(Subscription)
      .join(SubscriptionNode,SubscriptionNode.subscription_id==Subscription.id)
      .join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id)
      .filter(SubscriptionNode.node_id==node_id,SubscriptionProtocol.protocol=="openvpn",
        Subscription.status==SubscriptionStatus.ACTIVE,
        or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
        or_(Subscription.traffic_limit_bytes<=0,
            Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes)).all()}
    if not expected.issubset(active_ids) or db.get(Node,node_id).show_to_users:
        raise RuntimeError("OPENVPN_ENTITLEMENT_CHANGED")
    creds={int(c.subscription_id):c for c in db.query(ProtocolCredential).filter(
        ProtocolCredential.protocol=="openvpn",
        ProtocolCredential.subscription_id.in_(list(expected)),
    ).with_for_update().all()}
    host,port=ad._tunnel_access_endpoint(db,node,"openvpn")
    transport=ad._transport(db,node_id,"openvpn")
    proto="udp" if "udp" in transport else "tcp-client"
    saved=0
    for sub in selected:
        sid=int(sub.id)
        row=by_id[sid]
        ovpn=f"""client
dev tun
proto {proto}
remote {host} {int(port)}
redirect-gateway def1
tun-mtu 1200
mssfix 1160
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
verb 3
data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305
auth SHA256
<ca>
{outcome['ca']}
</ca>
<cert>
{row['certificate']}
</cert>
<key>
{row['private_key']}
</key>
"""
        cred=creds.get(sid)
        if cred is None:
            cred=ProtocolCredential(subscription_id=sid,protocol="openvpn")
            db.add(cred)
        items=ad._autosync_credential_items(cred)
        if any(ad._autosync_item_node_id(x)==node_id for x in items):
            continue
        items.append({
            "node_id":node_id,"node":node.name,"server":host,"server_ip":host,
            "port":int(port),"transport":transport,"central_pki":False,
            "filename":str(sub.account_username or f"user{sid}")+"-"+str(node.name)+".ovpn",
            "config":ovpn,
        })
        cred.config_text_encrypted=ad._enc(items)
        cred.is_active=True
        saved+=1
    db.commit()
    print("CENTRAL_EASYRSA_OPENVPN_RESULT",json.dumps({
        "node_id":node_id,"selected":len(selected),"centrally_saved":saved,
        "service_restarts":0,"node_remains_hidden":True,
    }),flush=True)
    return saved


async def run(opts):
    with SessionLocal() as db:
        if opts.apply:
            node=db.get(Node,int(opts.node_id))
            if node is None or node.show_to_users:
                raise RuntimeError("NODE_MUST_REMAIN_HIDDEN")
            health=await asyncio.wait_for(
                verify_new_exit_readiness(db,opts.node_id, allow_partial=True),timeout=510,
            )
            if not health.get("ok") or "openvpn" not in health.get("ready_protocols", ()):
                raise RuntimeError("STAGED_PROTOCOL_READINESS_FAILED")
        total=0
        for _ in range(25 if opts.all and opts.apply else 1):
            count=await one_cycle(db,opts.node_id,opts.limit,opts.apply)
            total+=count
            if not opts.apply or count==0:break
        print("CENTRAL_EASYRSA_OPENVPN_SUMMARY",json.dumps({
            "node_id":opts.node_id,"new_items":total,"node_remains_hidden":True,
        }),flush=True)


if __name__=="__main__":
    opts=parse_args()
    try:
        asyncio.run(run(opts))
    except Exception as exc:
        print("CENTRAL_EASYRSA_OPENVPN_STOP",{
            "node_id":opts.node_id,"error_type":type(exc).__name__,
        },flush=True)
        raise SystemExit(2)
