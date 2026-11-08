#!/usr/bin/env python3
"""Independent Mieru presence-only accounting on authoritative node telemetry.

This subprocess isolates short Mieru probes from slow WireGuard/Sudoku sweeps.
It does not modify Mieru node services, credentials, ports, byte counters,
or other protocols. The canonical _mark_presence handles admission and close.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import sys
import time
from pathlib import Path
from sqlalchemy import or_

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.models import Node, NodeType
from app.node_runtime_connection import connect_protocol_runtime
from app.services.accounting_device_map_batch_v1 import install_accounting_device_batch_cache
from app.services import modern_quota_runtime_v257 as canonical

INTERVAL_SECONDS = 20.0
LOCK_FILE = Path("/run/twinpanel-mieru-fast-presence-v1.lock")


async def reconcile_once() -> dict:
    db = SessionLocal()
    output = []
    try:
        node_ids = [
            int(row[0]) for row in db.query(Node.id).filter(
                Node.retired_at.is_(None),
                or_(Node.node_type == NodeType.EXIT, Node.agent_url == "local://core"),
            ).order_by(Node.id.asc()).all()
        ]
        db.commit()
        for node_id in node_ids:
            conn = None
            try:
                # Build canonical device/identity mapping; never derive identity
                # from source IP or use the amount of traffic as presence.
                devices = [
                    item for item in canonical.build_node_devices(db, node_id)
                    if str(item.get("protocol") or "").lower() == "mieru"
                ]
                db.commit()
                if not devices:
                    continue
                node = db.get(Node, node_id)
                conn = await asyncio.wait_for(
                    connect_protocol_runtime(node, db), timeout=12.0
                )
                db.commit()
                ok, rows, error = await asyncio.wait_for(
                    canonical._collect_mieru(conn), timeout=12.0
                )
                # Ensure SSH connections are released BEFORE DB mutation.
                conn.close()
                try:
                    await asyncio.wait_for(conn.wait_closed(), timeout=3.0)
                except Exception:
                    pass
                conn = None
                db.commit()
                if not ok:
                    output.append({"node_id": node_id, "ok": False,
                                   "error": str(error or "mieru_probe_failed")[:160]})
                    continue
                result = canonical._apply_mieru_presence(
                    db, node=node, devices=devices, rows=rows,
                )
                db.commit()
                output.append({
                    "node_id": node_id,
                    "ok": True,
                    "matched": result.get("matched"),
                    "online": result.get("online"),
                    "opened": result.get("opened"),
                    "closed": result.get("closed"),
                })
            except asyncio.CancelledError:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                output.append({
                    "node_id": node_id, "ok": False,
                    "error": f"{type(exc).__name__}:{str(exc)[:160]}",
                })
            finally:
                if conn is not None:
                    conn.close()
                    try:
                        await asyncio.wait_for(conn.wait_closed(), timeout=3.0)
                    except Exception:
                        pass
        return {"ok": all(x["ok"] for x in output), "nodes": output}
    finally:
        db.close()


async def main() -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock:
        # Distinct from slow modern quota flock: no process can monopolize
        # this fast presence-only worker with WireGuard reconciliation.
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        install_accounting_device_batch_cache()
        print(json.dumps({"event": "mieru_fast_presence_started",
                          "interval_seconds": INTERVAL_SECONDS}), flush=True)
        while True:
            started = time.monotonic()
            try:
                report = await reconcile_once()
                # Keep success logs compact to avoid filling journald.
                print(json.dumps({"event": "mieru_fast_presence",
                                  **report}, separators=(",", ":")), flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(json.dumps({"event": "mieru_fast_presence_crash",
                                  "error": f"{type(exc).__name__}:{str(exc)[:200]}"}),
                      flush=True)
            await asyncio.sleep(max(INTERVAL_SECONDS - (time.monotonic() - started), 0.5))


if __name__ == "__main__":
    asyncio.run(main())
