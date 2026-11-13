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
from app.services.accounting_device_map_batch_v1 import (
    install_accounting_device_batch_cache, build_presence_devices_for_protocols,
)
from app.services.central_runtime_ownership_v1 import is_central_node
from app.services.sudoku_shared_native_presence_v1 import (
    collect_shared_native_users, apply_shared_native_presence,
    apply_shared_native_counters,
)
from app.services.sudoku_legacy_systemd_accounting_v1 import (
    collect_legacy_unit_counters, apply_legacy_unit_counters,
)

LOCK_FILE = Path("/run/twinpanel-sudoku-fast-presence-v1.lock")
INTERVAL_SECONDS = 20.0


async def reconcile_once() -> dict:
    db = SessionLocal()
    # This brand-new presence-only session has no pending writes. The shared
    # batch builder may release credential/device SELECT transactions before
    # decrypting large identity maps; pending mutations still fail closed.
    db.info["twinpanel_v314_clean_lookup_session"] = True
    results = []
    try:
        node_ids = [
            int(row[0]) for row in db.query(Node.id).filter(
                Node.retired_at.is_(None),
                or_(Node.node_type == NodeType.EXIT, Node.agent_url == "local://core"),
            ).order_by(Node.id).all()
        ]
        db.commit()
        # Avoid decrypting every protocol's credentials for each Sudoku sweep.
        # This preserves per-node entitlement and authenticated device mapping.
        sudoku_by_node = build_presence_devices_for_protocols(
            db, source_protocols={"sudoku"},
        )
        db.commit()
        for node_id in node_ids:
            conn = None
            try:
                devices = sudoku_by_node.get(node_id, [])
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
                    connect_protocol_runtime(node, db, close_read_transaction_before_ssh=True), timeout=12,
                )
                db.commit()
                if central_shared:
                    ok, native, error = await asyncio.wait_for(
                        collect_shared_native_users(conn), timeout=14,
                    )
                    usage_ok, counters, usage_error = True, {}, None
                else:
                    ok, ports, error = await asyncio.wait_for(
                        canonical._collect_established_tcp_ports(conn), timeout=10,
                    )
                    # Per-user legacy units only; never inspect shared daemon
                    # or charge based on socket counts / estimated speeds.
                    usage_ok, counters, usage_error = await asyncio.wait_for(
                        collect_legacy_unit_counters(conn, devices), timeout=36,
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
                    usage=apply_shared_native_counters(
                        db,node=node,devices=devices,snapshot=native,
                    )
                else:
                    stats = canonical._apply_sudoku_presence(
                        db, node=node, devices=devices, established_ports=ports,
                    )
                    usage = (
                        apply_legacy_unit_counters(
                            db, node=node, devices=devices, counters=counters,
                        ) if usage_ok else {
                            "usage_events":0,"accepted_bytes":0,
                            "usage_supported":False,"baselined":0,
                        }
                    )
                db.commit()
                results.append({"node_id": node_id, "ok": bool(usage_ok),
                                "online": stats["online"],
                                "opened": stats["opened"],
                                "closed": stats["closed"],
                                "usage_events":usage["usage_events"],
                                "accepted_bytes":usage["accepted_bytes"],
                                "baselined":usage["baselined"],
                                "usage_supported":usage["usage_supported"],
                                **({"usage_error":usage_error} if not usage_ok else {})})
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
            report = None
            try:
                result = await reconcile_once()
                report = result
                print(json.dumps({"event": "sudoku_fast_presence", **result},
                                 separators=(",", ":")), flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(json.dumps({"event": "sudoku_fast_presence_crash",
                                  "error": f"{type(exc).__name__}:{str(exc)[:180]}"}),
                      flush=True)
            # A sweep that exceeds its cadence must not immediately begin
            # another full fleet scan. Retain 20s freshness on fast sweeps;
            # give failing collectors 15s of backoff, successful slow
            # collectors 5s of CPU/DB headroom before the next pass.
            min_rest = 15.0 if report is None or not report.get("ok", False) else 5.0
            await asyncio.sleep(max(INTERVAL_SECONDS - (time.monotonic() - started), min_rest))


if __name__ == "__main__":
    asyncio.run(main())
