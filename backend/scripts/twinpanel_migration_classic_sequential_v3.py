"""Idempotent, bounded direct Classic credential provisioning for imported accounts."""
from __future__ import annotations
import asyncio
import inspect
import fcntl
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
BACKEND_ROOT = Path("/opt/twinpanel/current/backend")
if not BACKEND_ROOT.exists():
    BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
from app.database import SessionLocal
from app.models import Node, Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus, ProtocolCredential, User
from app.migration_import_models import MigrationImportRecord
from app.routers import account_delivery as ad
from sqlalchemy import or_
logging.getLogger('asyncssh').setLevel(logging.WARNING)
SOURCES=('eylan','sanaei','marzban','pasargad')
PROTOCOL=os.getenv('CLASSIC_ONLY_PROTOCOL','openvpn').strip().lower()
assert PROTOCOL in {'openvpn','cisco','l2tp','wireguard'}
PROTOCOLS=(PROTOCOL,)
PER_NODE=int(os.getenv('CLASSIC_DIRECT_BATCH_PER_NODE','3'))
NODE_IDS=tuple(int(x) for x in os.getenv('CLASSIC_DIRECT_NODE_IDS','6').split(','))
def healthy():
    # An overloaded API can miss one readiness probe without being down.
    # Wait through transient congestion before stopping credential writes.
    for attempt in range(4):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8095/health/ready",timeout=7) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        if attempt < 3:
            time.sleep(2)
    return False
async def one_node(db,node_id,*,subscription_id: int | None = None):
    node=db.get(Node,node_id)
    now=datetime.utcnow()
    eligible_query=(db.query(Subscription).join(MigrationImportRecord, MigrationImportRecord.subscription_id==Subscription.id)
          .join(SubscriptionNode, SubscriptionNode.subscription_id==Subscription.id)
          .join(SubscriptionProtocol, SubscriptionProtocol.subscription_id==Subscription.id)
          .filter(MigrationImportRecord.source.in_(SOURCES),
                  SubscriptionProtocol.protocol==PROTOCOL,
                  SubscriptionNode.node_id==node_id,
                  Subscription.status==SubscriptionStatus.ACTIVE,
                  or_(Subscription.expires_at.is_(None),Subscription.expires_at>now),
                  or_(Subscription.traffic_limit_bytes<=0,Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes)))
    if subscription_id is not None:
        eligible_query=eligible_query.filter(Subscription.id==int(subscription_id))
    subs=eligible_query.order_by(Subscription.id.asc()).all()
    # Prefetch credential records once per node (avoid per-user SELECT).
    subscription_ids = [int(sub.id) for sub in subs]
    existing_credentials = {
        int(cred.subscription_id): cred
        for cred in (
            db.query(ProtocolCredential)
            .filter(
                ProtocolCredential.protocol == PROTOCOL,
                ProtocolCredential.subscription_id.in_(subscription_ids),
            ).all()
        )
    } if subscription_ids else {}
    succeeded=0
    skipped=0
    failed=0
    shared_conn=None
    try:
        for sub in subs:
            if succeeded>=PER_NODE:break
            for protocol in PROTOCOLS:
                if succeeded>=PER_NODE:break
                if not bool(getattr(node,'enable_'+protocol,False)):continue
                cred=existing_credentials.get(int(sub.id))
                items=ad._autosync_credential_items(cred)
                if any(ad._autosync_item_node_id(x)==node_id for x in items):
                    skipped+=1
                    continue
                # Most migrated users already have this node; only read User,
                # identity, and current status for an actually missing pair.
                user=db.get(User,sub.user_id)
                if not user:
                    continue
                username=sub.account_username or ad._safe_username(sub,user)
                password=sub.account_password_encrypted or ad._numeric_secret(8)
                # Guard repeat at write-time: no credentials for expired or exhausted users.
                db.refresh(sub)
                if sub.status!=SubscriptionStatus.ACTIVE or (sub.expires_at and sub.expires_at<=datetime.utcnow()) or (sub.traffic_limit_bytes>0 and sub.traffic_used_bytes>=sub.traffic_limit_bytes):
                    continue
                if not healthy():
                    print('API_UNHEALTHY_STOP',flush=True)
                    return (2,succeeded)
                try:
                    if protocol=='cisco':
                        item=await asyncio.wait_for(ad._cisco(db,node,sub,user,username,password),timeout=90)
                    elif protocol=='l2tp':
                        item=await asyncio.wait_for(ad._l2tp(db,node,sub,user,username,password),timeout=90)
                    elif protocol=='openvpn':
                        if 'reusable_connection' in inspect.signature(ad._openvpn).parameters:
                            if shared_conn is None and not ad.is_openvpn_central_pki_enabled(db):
                                shared_conn=await asyncio.wait_for(ad.ssh_connect_saved(node,db),timeout=30)
                            item=await asyncio.wait_for(ad._openvpn(db,node,sub,user,reusable_connection=shared_conn),timeout=180)
                        else:
                            item=await asyncio.wait_for(ad._openvpn(db,node,sub,user),timeout=180)
                    elif protocol=='wireguard':
                        item=await asyncio.wait_for(ad._wireguard(db,node,sub,user),timeout=90)
                    else:
                        raise ValueError("unsupported protocol")
                    if cred is None:
                        cred=ProtocolCredential(subscription_id=sub.id,protocol=protocol)
                        db.add(cred)
                        existing_credentials[int(sub.id)]=cred
                    items.append(item)
                    cred.config_text_encrypted=ad._enc(items)
                    cred.is_active=True
                    if protocol in ('cisco','l2tp'):
                        cred.username=username
                        cred.secret_encrypted=ad._enc({'password':password})
                    if not sub.account_username:sub.account_username=username
                    if not sub.account_password_encrypted:sub.account_password_encrypted=password
                    db.commit()
                    succeeded+=1
                    print('CLASSIC_DIRECT_COMMITTED',{'node':node_id,'protocol':protocol,'count':succeeded},flush=True)
                except Exception as e:
                    db.rollback()
                    failed+=1
                    print('CLASSIC_DIRECT_ERROR',{'node':node_id,'protocol':protocol,'type':type(e).__name__,'detail':str(e)[:120] if isinstance(e,TypeError) else ''},flush=True)
                    if failed >= 3 and succeeded == 0:
                        break
    finally:
        if shared_conn is not None:
            shared_conn.close()
            await shared_conn.wait_closed()
    print('CLASSIC_NODE_DONE',{'node':node_id,'protocol':PROTOCOL,'committed':succeeded,'reused':skipped,'failed':failed},flush=True)
    # Keep committed progress when an occasional per-account DB/SSH error
    # occurs. An all-failure cycle still stops and never advances phases.
    return (0 if failed==0 or succeeded>0 else 3, succeeded)
async def main():
    with open('/run/twinpanel-migration-classic-direct.lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cycles=min(240,max(1,int(os.getenv('CLASSIC_DIRECT_MAX_CYCLES','1'))))
        for cycle in range(cycles):
            if os.getloadavg()[0]>12 or not healthy():
                print('CLASSIC_SAFETY_STOP',{'cycle':cycle},flush=True)
                return 2
            total=0
            node_errors=[]
            for node_id in NODE_IDS:
                with SessionLocal() as db:
                    rc,committed=await one_node(db,node_id)
                    if rc:
                        node_errors.append((node_id,rc))
                        print('CLASSIC_NODE_RETRY_PENDING',{'node':node_id,'exit':rc},flush=True)
                    total+=committed
                await asyncio.sleep(1)
            print('CLASSIC_CYCLE_COMPLETE',{'cycle':cycle,'new_credentials':total,'node_errors':node_errors},flush=True)
            if total==0 and node_errors:
                return 3
            if total==0:
                print('CLASSIC_DIRECT_DONE',flush=True)
                return 0
            await asyncio.sleep(3)
    print('CLASSIC_CYCLE_LIMIT_REACHED',{'protocol':PROTOCOL,'cycles':cycles},flush=True)
    return 4
if __name__=='__main__':raise SystemExit(asyncio.run(main()))