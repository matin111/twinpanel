#!/usr/bin/env python3
"""Independent, presence-only Sudoku monitor using per-user assigned TCP port.

Never changes Sudoku service, credentials, firewall or quota byte counters.
Keeps only a bounded online/offline session state via the canonical contract.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
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
from app.services import modern_quota_runtime_v257 as canonical
from app.services.accounting_device_map_batch_v1 import install_accounting_device_batch_cache
from app.services.central_runtime_ownership_v1 import is_central_node
from app.services.sudoku_shared_native_presence_v1 import (
    collect_shared_native_users, apply_shared_native_presence,
)

LOCK_FILE = Path("/run/twinpanel-sudoku-fast-presence-v1.lock")
INTERVAL_SECONDS = 20.0


async def reconcile_once() -> dict:
    db = SessionLocal()
    results = []
    try:
        node_ids = [
            int(row[0]) for row in db.query(Node.id).filter(
                Node.retired_at.is_(None),
                or_(Node.node_type == NodeType.EXIT, Node.agent_url == "local://core"),
            ).order_by(Node.id).all()
        ]
        db.commit()
        for node_id in node_ids:
            conn = None
            try:
                devices = [
                    d for d in canonical.build_node_devices(db, node_id)
                    if str(d.get("protocol") or "").lower() == "sudoku"
                ]
                db.commit()
                if not devices:
                    continue
                # Registered published central Exits have ONE shared port for
                # every account. No per-user presence may be inferred from it.
                central_shared = is_central_node(db, node_id)
                node = db.get(Node, node_id)
                # This is a read-only lookup. Release the PostgreSQL
                # transaction BEFORE awaiting SSH (up to 12 seconds).
                # SessionLocal(expire_on_commit=False) keeps node fields.
                db.commit()
                conn = await asyncio.wait_for(
                    connect_protocol_runtime(node, db), timeout=12,
                )
                db.commit()
                if central_shared:
                    ok, native, error = await asyncio.wait_for(
                        collect_shared_native_users(conn), timeout=14,
                    )
                else:
                    ok, ports, error = await asyncio.wait_for(
                        canonical._collect_established_tcp_ports(conn), timeout=10,
                    )
                conn.close()
                try:
                    await asyncio.wait_for(conn.wait_closed(), timeout=3)
                except Exception:
                    pass
                conn = None
                db.commit()
                if not ok:
                    results.append({"node_id": node_id, "ok": False,
                                    "error": str(error or "sudoku_probe_failed")[:160]})
                    continue
                # The native controller is the ONLY per-user source for
                # centrally owned Sudoku. Legacy Exits retain their old
                # dedicated-port checks until their verified retirement.
                if central_shared:
                    stats = apply_shared_native_presence(
                        db, node=node, devices=devices, snapshot=native,
                    )
                else:
                    stats = canonical._apply_sudoku_presence(
                        db, node=node, devices=devices, established_ports=ports,
                    )
                db.commit()
                results.append({"node_id": node_id, "ok": True,
                                "online": stats["online"],
                                "opened": stats["opened"],
                                "closed": stats["closed"]})
            except asyncio.CancelledError:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                results.append({"node_id": node_id, "ok": False,
                                "error": f"{type(exc).__name__}:{str(exc)[:160]}"})
            finally:
                if conn is not None:
                    conn.close()
                    try:
                        await asyncio.wait_for(conn.wait_closed(), timeout=3)
                    except Exception:
                        pass
        return {"ok": all(x["ok"] for x in results), "nodes": results}
    finally:
        db.close()


async def main() -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        install_accounting_device_batch_cache()
        print("TWINPANEL_SUDOKU_FAST_PRESENCE_V1_ACTIVE", flush=True)
        while True:
            started = time.monotonic()
            try:
                result = await reconcile_once()
                print(json.dumps({"event": "sudoku_fast_presence", **result},
                                 separators=(",", ":")), flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(json.dumps({"event": "sudoku_fast_presence_crash",
                                  "error": f"{type(exc).__name__}:{str(exc)[:180]}"}),
                      flush=True)
            await asyncio.sleep(max(INTERVAL_SECONDS - (time.monotonic() - started), .5))


if __name__ == "__main__":
    asyncio.run(main())
