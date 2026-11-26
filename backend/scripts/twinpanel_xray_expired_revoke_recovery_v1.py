#!/usr/bin/env python3
"""Opt-in, node-scoped repair for old failed Xray revokes of NON-entitled users.

Default is READ ONLY. Live mode requires both --apply and an exact node ID
confirmation. Does not mutate subscription balances, dates, statuses or
existing command audit rows. Uses hot user-scoped HandlerService changes with
no Xray restart; stop the batch at the first unverified outcome.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import shlex
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from app.database import SessionLocal
from app.models import Node, NodeStatus, NodeType
from app.routers.provision import ssh_connect_saved
from app.services.xray_hot_client_revoke_v1 import hot_revoke_script

logging.getLogger("asyncssh").setLevel(logging.WARNING)

_CANDIDATES = text("""
SELECT DISTINCT CAST(q.payload->>'subscription_id' AS bigint) AS sid
FROM quota_node_commands q
JOIN subscriptions s ON s.id=CAST(q.payload->>'subscription_id' AS bigint)
WHERE q.node_id=:node_id AND q.command_type='revoke_subscription'
  AND q.status='failed' AND q.payload->>'protocol'='xray'
  AND (
       (s.status='EXPIRED' AND s.expires_at<now())
       OR s.status IN ('SUSPENDED','CANCELED')
  )
  AND NOT EXISTS (
       SELECT 1 FROM quota_node_commands r
       WHERE r.node_id=q.node_id AND r.command_type='restore_subscription'
         AND r.payload->>'subscription_id'=q.payload->>'subscription_id'
         AND r.issued_at>q.issued_at
  )
ORDER BY sid
""")
_FRESH = text("""
SELECT count(*) FROM (
SELECT DISTINCT CAST(q.payload->>'subscription_id' AS bigint)
FROM quota_node_commands q
JOIN subscriptions s ON s.id=CAST(q.payload->>'subscription_id' AS bigint)
WHERE q.node_id=:node_id AND q.command_type='revoke_subscription'
  AND q.status='failed' AND q.payload->>'protocol'='xray'
  AND CAST(q.payload->>'subscription_id' AS bigint)=:sid
  AND (
       (s.status='EXPIRED' AND s.expires_at<now())
       OR s.status IN ('SUSPENDED','CANCELED')
  )
  AND NOT EXISTS (
       SELECT 1 FROM quota_node_commands r
       WHERE r.node_id=q.node_id AND r.command_type='restore_subscription'
         AND r.payload->>'subscription_id'=q.payload->>'subscription_id'
         AND r.issued_at>q.issued_at
  )
) eligible
""")
_REMOTE_SCAN = """import json,subprocess
from pathlib import Path
p=Path('/usr/local/etc/xray/config.json')
r=subprocess.run(['systemctl','is-active','xray'],capture_output=True,text=True,timeout=5)
if r.stdout.strip()!='active' or not p.is_file():
 print(json.dumps({'ok':False,'reason':'node_xray_not_installed_or_active'}))
else:
 doc=json.loads(p.read_text())
 u={str(c.get('email')) for row in doc.get('inbounds',[])
    if isinstance(row,dict) and row.get('protocol')=='vless'
    for c in row.get('settings',{}).get('clients',[]) if isinstance(c,dict)}
 names=__TARGETS__
 print(json.dumps({'ok':True,'present':[int(i) for i in names if f'mv-{i}@twinpanel' in u]}))
"""
_REMOTE_BACKUP = """from pathlib import Path
import os,shutil
p=Path('/usr/local/etc/xray/config.json')
backup=Path('/usr/local/etc/xray/config.tp-failed-revokes-20261126.before')
if p.is_symlink() or not p.is_file():raise RuntimeError('XRAY_CONFIG_NOT_VERIFIED')
if backup.exists():
 if backup.is_symlink() or not backup.is_file():raise RuntimeError('XRAY_BACKUP_UNSAFE')
else:
 with open(p,'rb') as src,open(backup,'xb') as dst:
  os.fchmod(dst.fileno(),0o600)
  shutil.copyfileobj(src,dst)
  dst.flush();os.fsync(dst.fileno())
print('NODE_XRAY_SAFE_BACKUP_OK')
"""
_REMOTE_PID = "systemctl show xray -p MainPID --value"


def _eligible(db, node_id: int) -> list[int]:
    db.execute(text("SET LOCAL statement_timeout = '7000ms'"))
    values = [int(row[0]) for row in db.execute(_CANDIDATES, {"node_id":node_id})]
    db.rollback()
    return values


def _still_eligible(node_id: int, sid: int) -> bool:
    with SessionLocal() as db:
        try:
            db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            result = db.execute(_FRESH, {"node_id":node_id,"sid":sid}).scalar()
            return bool(result)
        finally:
            db.rollback()


def _decode_node_output(value: str) -> dict:
    raw = value.strip()
    if len(raw) > 150_000:
        raise RuntimeError("XRAY_REMOTE_REPORT_TOO_LARGE")
    return json.loads(raw.splitlines()[-1])


async def _remote(conn, code: str, *, timeout: int = 30) -> str:
    result = await asyncio.wait_for(
        conn.run("python3 -c " + shlex.quote(code),check=False,timeout=timeout),
        timeout=timeout+3,
    )
    if int(result.exit_status or 0):
        # Intentionally do NOT disclose SSH stderr; it may include secrets.
        raise RuntimeError("XRAY_REMOTE_COMMAND_FAILED")
    return str(result.stdout or "")


async def reconcile(node_id: int, *, limit: int, apply: bool, pause_seconds: float) -> dict:
    with SessionLocal() as db:
        ids = _eligible(db, node_id)
        node = db.get(Node,node_id)
        if (node is None or node.retired_at is not None
                or node.node_type!=NodeType.EXIT or node.status!=NodeStatus.ONLINE):
            raise RuntimeError("XRAY_EXIT_NOT_ELIGIBLE")
        db.commit()
        conn = await asyncio.wait_for(
            ssh_connect_saved(node,db,close_read_transaction_before_ssh=True),
            timeout=18,
        )
        db.commit()
        try:
            scan=_REMOTE_SCAN.replace("__TARGETS__",repr(ids))
            report = _decode_node_output(await _remote(conn,scan,timeout=15))
            if not report.get("ok"):
                raise RuntimeError(str(report.get("reason") or "XRAY_REMOTE_SCAN_UNAVAILABLE"))
            present=[int(s) for s in report.get("present") or []]
            if not set(present).issubset(set(ids)):
                raise RuntimeError("XRAY_REMOTE_IDENTITY_CONFLICT")
            selected=present[:limit]
            if not apply:
                return {
                    "ok":True,"mode":"DRY_RUN","node_id":node_id,
                    "old_failed_non_entitled":len(ids),
                    "still_present_on_node":len(present),
                    "selected":len(selected),"applied":0,
                }
            if not selected:
                return {
                    "ok":True,"mode":"APPLY","node_id":node_id,
                    "old_failed_non_entitled":len(ids),
                    "still_present_on_node":0,"applied":0,
                }
            await _remote(conn,_REMOTE_BACKUP,timeout=12)
            before=(await conn.run(_REMOTE_PID,check=False,timeout=5)).stdout.strip()
            if not before.isdigit() or int(before)<=0:
                raise RuntimeError("XRAY_RUNNING_PID_MISSING")
            applied=unchanged=skipped=0
            for sid in selected:
                if not _still_eligible(node_id,sid):
                    skipped+=1
                    continue
                # Every user-scoped operation locks the same node config,
                # validates a staged version, uses localhost API and refuses
                # any global service restart. Concurrent config changes
                # abort and roll back the just-touched live identity.
                result = _decode_node_output(
                    await _remote(conn,hot_revoke_script(sid),timeout=32)
                )
                if result.get("ok") is not True or result.get("live_restart") is not False:
                    raise RuntimeError("XRAY_HOT_REVOKE_NOT_VERIFIED")
                applied+=int(result.get("changed") is True)
                unchanged+=int(result.get("changed") is False)
                if pause_seconds:
                    await asyncio.sleep(pause_seconds)
            after=(await conn.run(_REMOTE_PID,check=False,timeout=5)).stdout.strip()
            if after!=before:
                raise RuntimeError("XRAY_UNEXPECTED_PROCESS_RESTART")
            return {
                "ok":True,"mode":"APPLY","node_id":node_id,
                "old_failed_non_entitled":len(ids),
                "still_present_on_node":len(present),
                "selected":len(selected),
                "applied":applied,"already_absent":unchanged,
                "skipped_now_entitled":skipped,
                "xray_process_unchanged":True,
                "customer_balances_changed":False,
                "historical_command_rows_edited":False,
            }
        finally:
            conn.close()
            try:
                await asyncio.wait_for(conn.wait_closed(),timeout=4)
            except Exception:
                pass


def main() -> None:
    p=argparse.ArgumentParser(description="Revoke only STILL-expired historical Xray users")
    p.add_argument("--node-id",type=int,required=True)
    p.add_argument("--limit",type=int,default=5)
    p.add_argument("--apply",action="store_true")
    p.add_argument("--confirm-node-id",type=int)
    p.add_argument("--pause-ms",type=int,default=150)
    a=p.parse_args()
    if a.node_id<=0 or not 1<=a.limit<=30 or not 0<=a.pause_ms<=2000:
        p.error("invalid bounded node/limit/pause")
    if a.apply and a.confirm_node_id!=a.node_id:
        p.error("apply requires exact --confirm-node-id")
    result=asyncio.run(reconcile(
        a.node_id,limit=a.limit,apply=a.apply,
        pause_seconds=a.pause_ms/1000,
    ))
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
