#!/usr/bin/env python3
"""Idempotent, health-guarded WireGuard-only backfill for active imported accounts."""
from __future__ import annotations
import asyncio
import fcntl
import logging
import os
import sys
sys.path.insert(0,"/opt/twinpanel/current/backend")
import urllib.request
from datetime import datetime
from sqlalchemy import or_
from app.database import SessionLocal
from app.migration_import_models import MigrationImportRecord
from app.models import Node, NodeStatus, NodeType, ProtocolCredential, Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus, User
from app.routers import account_delivery as ad

logging.getLogger("asyncssh").setLevel(logging.WARNING)
SOURCES = ("eylan", "sanaei", "marzban", "pasargad")
NODE_IDS = (1, 6, 7, 11)
MAX_PER_NODE = min(12, max(1, int(os.getenv("MIGRATION_WG_LIMIT_PER_NODE", "2"))))

def healthy():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8095/health/ready",timeout=4) as response:
            return response.status==200
    except Exception:
        return False

def eligible(db, node_id):
    return (db.query(Subscription)
            .join(MigrationImportRecord,MigrationImportRecord.subscription_id==Subscription.id)
            .join(SubscriptionNode,SubscriptionNode.subscription_id==Subscription.id)
            .join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id)
            .filter(MigrationImportRecord.source.in_(SOURCES),
                    SubscriptionNode.node_id==node_id,
                    SubscriptionProtocol.protocol=="wireguard",
                    Subscription.status==SubscriptionStatus.ACTIVE,
                    or_(Subscription.expires_at.is_(None),Subscription.expires_at>datetime.utcnow()),
                    or_(Subscription.traffic_limit_bytes<=0,Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes))
            .order_by(Subscription.id).distinct().all())

async def work():
    with open("/run/twinpanel-migration-wireguard-batch.lock","a+") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print("WG_BATCH_ALREADY_RUNNING",flush=True)
            return 3
        total=0
        for node_id in NODE_IDS:
            if os.getloadavg()[0]>8 or not healthy():
                print("WG_BATCH_SAFETY_STOP",{"node":node_id,"load":round(os.getloadavg()[0],2)},flush=True)
                return 2
            db=SessionLocal()
            try:
                node=db.get(Node,node_id)
                if not node or node.node_type!=NodeType.EXIT or node.status!=NodeStatus.ONLINE or not node.enable_wireguard:
                    print("WG_NODE_SKIPPED",{"node":node_id},flush=True)
                    continue
                done=0
                for sub in eligible(db,node_id):
                    if done>=MAX_PER_NODE:
                        break
                    if os.getloadavg()[0]>8 or not healthy():
                        print("WG_BATCH_SAFETY_STOP",{"node":node_id},flush=True)
                        return 2
                    cred=db.query(ProtocolCredential).filter(ProtocolCredential.subscription_id==sub.id,ProtocolCredential.protocol=="wireguard").first()
                    if cred is not None and cred.config_text_encrypted and ad._dec(cred.config_text_encrypted) is None:
                        print("WG_INVALID_EXISTING_CREDENTIAL_SKIPPED",{"node":node_id,"subscription":sub.id},flush=True)
                        continue
                    items=ad._autosync_credential_items(cred)
                    if any(ad._autosync_item_node_id(x)==node_id for x in items):
                        continue
                    user=db.get(User,sub.user_id)
                    if user is None:
                        continue
                    try:
                        item=await asyncio.wait_for(ad._wireguard(db,node,sub,user),timeout=65)
                        if cred is None:
                            cred=ProtocolCredential(subscription_id=sub.id,protocol="wireguard")
                            db.add(cred)
                        cred.config_text_encrypted=ad._enc(items+[item])
                        cred.is_active=True
                        db.commit()
                        done+=1
                        total+=1
                        print("WG_BATCH_COMMITTED",{"node":node_id,"subscription":sub.id,"address":item.get("address")},flush=True)
                    except Exception as e:
                        db.rollback()
                        print("WG_BATCH_ERROR",{"node":node_id,"type":type(e).__name__},flush=True)
                        break
                    await asyncio.sleep(0.35)
                print("WG_NODE_DONE",{"node":node_id,"new_credentials":done},flush=True)
            finally:
                db.close()
        print("WG_BATCH_DONE",{"new_credentials":total},flush=True)
        return 0

if __name__=="__main__":
    raise SystemExit(asyncio.run(work()))