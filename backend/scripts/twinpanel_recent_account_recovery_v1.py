#!/usr/bin/env python3
"""Durable, idempotent recovery for recently created ACTIVE subscriptions."""
import asyncio
import fcntl
import logging
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import func, or_

sys.path.insert(0, "/opt/twinpanel/current/backend")
logging.getLogger("asyncssh").setLevel(logging.WARNING)
from app.database import SessionLocal
from app.migration_import_models import MigrationImportRecord
from app.models import Subscription, SubscriptionProtocol, ProtocolCredential, SubscriptionStatus
from app.routers import modern_legacy_reconcile_v1 as recovery
from app.routers import modern_legacy_reconcile_lockfix_v2  # noqa: F401 - install guarded repair

MAX_ACCOUNTS = min(4, max(1, int(os.environ.get('RECENT_RECOVERY_MAX_ACCOUNTS','2'))))
MAX_PROTOCOLS = min(3, max(1, int(os.environ.get('RECENT_RECOVERY_MAX_PROTOCOLS','2'))))

def api_healthy():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8095/health/ready',timeout=3) as response:
            return response.status==200
    except Exception:return False

def get_incomplete():
    db=SessionLocal()
    try:
        cutoff=datetime.utcnow()-timedelta(days=30)
        ids=db.query(Subscription.id).join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id).outerjoin(MigrationImportRecord,MigrationImportRecord.subscription_id==Subscription.id).filter(
            MigrationImportRecord.subscription_id.is_(None),
            Subscription.status==SubscriptionStatus.ACTIVE,
            Subscription.created_at>=cutoff,
            or_(Subscription.expires_at.is_(None),Subscription.expires_at>datetime.utcnow()),
            or_(Subscription.traffic_limit_bytes<=0,Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes),
        ).group_by(Subscription.id).having(func.count(func.distinct(SubscriptionProtocol.protocol))>=6).order_by(Subscription.id.desc()).limit(350).all()
        candidates=[]
        for (id_,) in ids:
            selected={p for (p,) in db.query(SubscriptionProtocol.protocol).filter_by(subscription_id=id_).all()}
            existing={p for (p,) in db.query(ProtocolCredential.protocol).filter(
                ProtocolCredential.subscription_id==id_,ProtocolCredential.is_active.is_(True),
                ProtocolCredential.config_text_encrypted.isnot(None),ProtocolCredential.config_text_encrypted!=''
            ).all()}
            missing=sorted(selected-existing)
            if any(p in recovery.MODERN_PROTOCOL_KEYS for p in missing):
                candidates.append((id_,len(missing)))
        # Prioritize the largest missing sets instead of repeatedly starving
        # older, heavily incomplete new purchases behind nearly finished ones.
        return sorted(candidates, key=lambda item: (-item[1], item[0]))[:MAX_ACCOUNTS]
    finally:db.close()

async def main():
    with open('/run/twinpanel-recent-account-recovery.lock','a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('RECOVERY_ALREADY_RUNNING',flush=True);return 3
        if os.getloadavg()[0]>9 or not api_healthy():
            print('RECOVERY_SAFETY_STOP',flush=True);return 2
        for id_,missing in get_incomplete():
            if os.getloadavg()[0]>9 or not api_healthy():
                print('RECOVERY_SAFETY_STOP_ACCOUNT',id_,flush=True);return 2
            try:
                result=await asyncio.wait_for(recovery.reconcile_subscription_modern_accounts(id_,max_protocols=MAX_PROTOCOLS),timeout=210)
                print('RECOVERY_RESULT',{'id':id_,'missing_before':missing,'repaired':[r.get('protocol') for r in result.get('repaired',[])],'error_codes':[e.get('error','')[:130] for e in result.get('errors',[])][:5],'busy':result.get('busy',False)},flush=True)
            except Exception as exc:
                print('RECOVERY_ERROR',{'id':id_,'type':type(exc).__name__},flush=True)
            await asyncio.sleep(2)
        return 0

if __name__=='__main__':raise SystemExit(asyncio.run(main()))