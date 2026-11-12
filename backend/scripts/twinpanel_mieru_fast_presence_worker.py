#!/usr/bin/env python3
"""Independent Mieru presence and per-user traffic accounting on native node telemetry.

This subprocess isolates short Mieru probes from slow WireGuard/Sudoku sweeps.
It does not modify Mieru node services, credentials, ports, source byte counters,
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
from app.services.quota_node_sync import build_node_devices as build_mieru_node_devices

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
                # Do NOT invoke the worker-global cached all-protocol map:
                # it decrypts ~20k credentials while Mieru needs only its
                # own per-node identities. Exact canonical membership remains.
                devices = build_mieru_node_devices(
                    db, node_id, source_protocols={"mieru"},
                )
                db.commit()
                if not devices:
                    continue
                node = db.get(Node, node_id)
                # Node/identity reads must not leave an open transaction
                # over SSH and two 12-second authenticated probes.
                db.commit()
                conn = await asyncio.wait_for(
                    connect_protocol_runtime(node, db, close_read_transaction_before_ssh=True), timeout=12.0
                )
                db.commit()
                ok, rows, error = await asyncio.wait_for(
                    canonical._collect_mieru(conn), timeout=12.0
                )
                # The authoritative per-user persisted Mieru byte counters
                # live in this worker. V314 deliberately skips Mieru when
                # TP_MIERU_INDEPENDENT_WORKER=1, so collecting only presence
                # here silently disables central traffic billing.
                metrics_ok, metrics, metrics_error = await asyncio.wait_for(
                    canonical._collect_mieru_cumulative_metrics(conn),
                    timeout=12.0,
                )
                # Ensure SSH connections are released BEFORE DB mutation.
                conn.close()
                try:
                    await asyncio.wait_for(conn.wait_closed(), timeout=3.0)
                except Exception:
                    pass
                conn = None
                db.commit()
                presence = {}
                if ok:
                    presence = canonical._apply_mieru_presence(
                        db, node=node, devices=devices, rows=rows,
                    )
                    db.commit()
                # The billing ledger has its own transaction. A failed
                # online probe cannot suppress valid authenticated byte
                # counters; a failed byte probe never invents consumption.
                usage = {}
                if metrics_ok:
                    usage = canonical._apply_mieru_cumulative_metrics(
                        db, node=node, devices=devices, metrics=metrics,
                    )
                    db.commit()
                output.append({
                    "node_id": node_id,
                    "ok": bool(ok and metrics_ok),
                    "presence_ok": bool(ok),
                    "usage_ok": bool(metrics_ok),
                    "error": str(
                        error if not ok else metrics_error if not metrics_ok else ""
                    )[:140] or None,
                    "matched": presence.get("matched"),
                    "online": presence.get("online"),
                    "opened": presence.get("opened"),
                    "closed": presence.get("closed"),
                    "usage_matched": usage.get("matched", 0),
                    "baselined": usage.get("baselined", 0),
                    "usage_events": usage.get("usage_events", 0),
                    "accepted_bytes": usage.get("accepted_bytes", 0),
                    "rejected_counters": usage.get("rejected_counters", 0),
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
            report = None
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
            # A sweep that exceeds its cadence must not immediately begin
            # another full fleet scan. Retain 20s freshness on fast sweeps;
            # give failing collectors 15s of backoff, successful slow
            # collectors 5s of CPU/DB headroom before the next pass.
            min_rest = 15.0 if report is None or not report.get("ok", False) else 5.0
            await asyncio.sleep(max(INTERVAL_SECONDS - (time.monotonic() - started), min_rest))


if __name__ == "__main__":
    asyncio.run(main())
