#!/usr/bin/env python3
"""Targeted and resumable missing standalone credentials (one account/protocol).
Does not rotate any stored identity or change protocol/runtime settings.
"""
from __future__ import annotations
import asyncio
import fcntl
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import or_

sys.path.insert(0, str(Path("/opt/twinpanel/current/backend") if Path("/opt/twinpanel/current/backend/app").exists() else Path(__file__).resolve().parents[1]))
logging.getLogger("asyncssh").setLevel(logging.WARNING)
from app.database import SessionLocal
from app.migration_import_models import MigrationImportRecord
from app.models import Subscription, SubscriptionProtocol, ProtocolCredential, SubscriptionStatus
from app.quota_models import QuotaDevice
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.routers import modern_legacy_reconcile_v1 as legacy
from app.routers import modern_legacy_reconcile_lockfix_v2 as lockfix  # noqa: F401

SOURCES = ("eylan","sanaei","marzban","pasargad")
PROTOCOLS = ("mieru","trusttunnel","amneziawg","sudoku")
PROTOCOL = os.environ.get("STANDALONE_RECOVERY_PROTOCOL","").strip().lower()
STATE_FILE = Path("/var/lib/twinpanel/standalone-migration-recovery.json")
MAX_ACCOUNTS = max(1,min(8,int(os.environ.get("STANDALONE_RECOVERY_MAX_ACCOUNTS","1"))))
MAX_RUNTIME_SECONDS = 420

def sync_target_quota_device(subscription_id: int) -> dict:
    """Upsert only the new protocol identity, never rewrite full per-node snapshots.

    Node agents obtain their current quota payload from the API on demand.
    The separate 45s accounting loop already refreshes protocol telemetry.
    A legacy complete/inactive quota device must never be reactivated here.
    """
    db=SessionLocal()
    try:
        credential=db.query(ProtocolCredential).filter(
            ProtocolCredential.subscription_id==int(subscription_id),
            ProtocolCredential.protocol==PROTOCOL,
            ProtocolCredential.is_active.is_(True),
            ProtocolCredential.config_text_encrypted.isnot(None),
            ProtocolCredential.secret_encrypted.isnot(None),
        ).first()
        if credential is None:
            return {"ok":False,"reason":"credential_missing"}
        device=db.query(QuotaDevice).filter(
            QuotaDevice.subscription_id==int(subscription_id),
            QuotaDevice.protocol==PROTOCOL,
        ).order_by(QuotaDevice.id.asc()).first()
        if device is not None:
            return {"ok":str(device.status or "").strip().lower()=="active",
                    "mode":"existing_device"}
        sid=int(subscription_id)
        db.execute(pg_insert(QuotaDevice).values(
            subscription_id=sid,
            protocol=PROTOCOL,
            device_key=f"subscription:{sid}:{PROTOCOL}",
            credential_public_hash=f"legacy-backfill-{sid}-{PROTOCOL}",
            status="active",
        ).on_conflict_do_nothing(constraint="uq_quota_device_key"))
        db.commit()
        device=db.query(QuotaDevice).filter(
            QuotaDevice.subscription_id==sid,QuotaDevice.protocol==PROTOCOL,
        ).order_by(QuotaDevice.id.asc()).first()
        return {"ok":device is not None and str(device.status or "").strip().lower()=="active",
                "mode":"targeted_upsert"}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def healthy() -> bool:
    if os.getloadavg()[0] > 9:
        return False
    try:
        start=time.monotonic()
        with urllib.request.urlopen("http://127.0.0.1:8095/health/ready", timeout=4) as r:
            return r.status == 200 and time.monotonic()-start < 1.5
    except Exception:
        return False

def candidates(after_id: int = 0):
    db=SessionLocal()
    try:
        rows=(db.query(Subscription.id)
            .join(MigrationImportRecord,MigrationImportRecord.subscription_id==Subscription.id)
            .join(SubscriptionProtocol,SubscriptionProtocol.subscription_id==Subscription.id)
            .outerjoin(ProtocolCredential,
                (ProtocolCredential.subscription_id==Subscription.id) & (ProtocolCredential.protocol==PROTOCOL))
            .filter(MigrationImportRecord.source.in_(SOURCES),
                SubscriptionProtocol.protocol==PROTOCOL,
                Subscription.status==SubscriptionStatus.ACTIVE,
                or_(Subscription.expires_at.is_(None),Subscription.expires_at>datetime.now(timezone.utc).replace(tzinfo=None)),
                or_(Subscription.traffic_limit_bytes<=0,Subscription.traffic_used_bytes<Subscription.traffic_limit_bytes),
                ProtocolCredential.id.is_(None))
            .filter(Subscription.id > int(after_id))
            .group_by(Subscription.id).order_by(Subscription.id.asc()).limit(MAX_ACCOUNTS).all())
        ids=[int(id) for (id,) in rows]
        if ids or after_id<=0:
            return ids
        return candidates(0)
    finally:
        db.close()

async def run() -> int:
    global PROTOCOL
    if PROTOCOL and PROTOCOL not in PROTOCOLS:
        raise ValueError("invalid standalone protocol")
    began=time.monotonic()
    with open("/run/twinpanel-migration-standalone-recovery.lock","a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print("STANDALONE_BUSY",flush=True)
            return 3
        if not healthy():
            print("STANDALONE_STOP_API",flush=True)
            return 2
        try:
            state=json.loads(STATE_FILE.read_text())
        except (FileNotFoundError,ValueError):
            state={"next":0,"cursor":{}}
        state.setdefault("cursor",{})
        if not PROTOCOL:
            PROTOCOL=PROTOCOLS[int(state.get("next",0))%len(PROTOCOLS)]
            state["next"]=(int(state.get("next",0))+1)%len(PROTOCOLS)
        ids=candidates(int(state["cursor"].get(PROTOCOL,0)))
        # Persist rotation before provisioning so a transient account error
        # cannot permanently starve other standalone protocols.
        STATE_FILE.parent.mkdir(parents=True,exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))

        print("STANDALONE_WORK",{"protocol":PROTOCOL,"ids":ids},flush=True)
        # Register only the new QuotaDevice; full node quota exports are
        # generated on demand by the API and accounting service.
        lockfix._sync_repaired_quota_in_thread = sync_target_quota_device
        orig = legacy._selected_modern_protocols
        # This worker is a separate process. Restrict the existing audited
        # reconciliation/PG advisory lock path to the desired protocol only.
        legacy._selected_modern_protocols=lambda db, sid: [p for p in orig(db,sid) if p==PROTOCOL]
        for sid in ids:
            if time.monotonic()-began > MAX_RUNTIME_SECONDS:
                print("STANDALONE_TIME_BUDGET_STOP",flush=True)
                break
            if not healthy():
                print("STANDALONE_STOP_API",flush=True)
                return 2
            try:
                result=await asyncio.wait_for(
                    legacy.reconcile_subscription_modern_accounts(sid,max_protocols=1),
                    timeout=235,
                )
                print("STANDALONE_RESULT",{
                    "id":sid,"protocol":PROTOCOL,
                    "repaired":[x.get("protocol") for x in result.get("repaired",[])],
                    "error_codes":[str(x.get("error",""))[:105] for x in result.get("errors",[])][:5],
                    "busy":result.get("busy",False)
                },flush=True)
            except Exception as exc:
                print("STANDALONE_ERROR",{"id":sid,"type":type(exc).__name__},flush=True)
            finally:
                state["cursor"][PROTOCOL]=sid
                tmp=STATE_FILE.with_suffix(".tmp")
                tmp.write_text(json.dumps(state,separators=(",",":")))
                tmp.replace(STATE_FILE)
        return 0

if __name__=="__main__":
    raise SystemExit(asyncio.run(run()))