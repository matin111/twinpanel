#!/usr/bin/env python3
"""Independent authenticated Naive presence, never mutate the VPN dataplane.

The full sing-box accounting worker still owns quota bytes and cursor updates.
This narrow poller only refreshes canonical sessions for actually observed,
authenticated Naive connections. Its sole purpose is to prevent a legacy
cursor conflict or slow unrelated protocol from starving true online state.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import sys
import time
from pathlib import Path
from sqlalchemy import or_

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import Node, NodeType
from app.node_runtime_connection import connect_protocol_runtime
from app.services.accounting_device_map_batch_v1 import (
    install_accounting_device_batch_cache, build_presence_devices_for_protocols,
)
from app.services import singbox_native_accounting_v265 as native

INTERVAL_SECONDS = 20.0
LOCK_FILE = Path("/run/twinpanel-naive-live-presence-v1.lock")


async def reconcile_once() -> dict:
    db = SessionLocal()
    # This brand-new presence-only session has no pending writes. The shared
    # batch builder may release credential/device SELECT transactions before
    # decrypting large identity maps; pending mutations still fail closed.
    db.info["twinpanel_v314_clean_lookup_session"] = True
    results = []
    try:
        nodes = (
            db.query(Node)
            .filter(
                Node.retired_at.is_(None),
                or_(Node.node_type == NodeType.EXIT, Node.agent_url == "local://core"),
            )
            .order_by(Node.id.asc())
            .all()
        )
        # Identity mapping is loaded in one batch and is never inferred by IP.
        # One SQL/decryption pass for Naive alone, not every active protocol.
        # The canonical auth/identity mapping and quota device IDs are retained.
        by_node = build_presence_devices_for_protocols(
            db, source_protocols={"naive", "naiveproxy"},
        )
        db.commit()
        # Bias toward currently connected Naive users; avoid starving the
        # known live node behind lengthy remote probes for idle nodes.
        from app.quota_models import QuotaSession
        recent_node_ids = {
            int(node_id) for (node_id,) in (
                db.query(QuotaSession.node_id)
                .filter(
                    QuotaSession.protocol == "naive",
                    QuotaSession.status == "active",
                )
                .distinct().all()
            )
        }
        db.commit()
        ordered = sorted(nodes, key=lambda n: (int(n.id) not in recent_node_ids, int(n.id)))
        for node in ordered:
            node_id = int(node.id)
            devices = by_node.get(node_id, [])
            if not devices:
                continue
            conn = None
            try:
                # Previous per-node session/identity lookups may open a
                # read transaction. Never hold it across slow SSH.
                db.commit()
                conn = await asyncio.wait_for(connect_protocol_runtime(node, db, close_read_transaction_before_ssh=True), timeout=12)
                db.commit()
                ok, snapshot, error = await asyncio.wait_for(
                    native.collect_singbox_snapshot(conn), timeout=18,
                )
                conn.close()
                try:
                    await asyncio.wait_for(conn.wait_closed(), timeout=3)
                except Exception:
                    pass
                conn = None
                db.commit()
                if not ok or snapshot is None:
                    results.append({"node_id": node_id, "ok": False,
                                    "error": str(error or "snapshot_unavailable")[:120]})
                    continue
                # Only the genuine Naive inbound with authenticated per-user
                # identity can open/touch a session. Never fabricate traffic.
                report = native._refresh_authenticated_live_presence(
                    db, node=node, grouped={"naive": devices}, snapshot=snapshot,
                )
                results.append({"node_id": node_id, "ok": report["failed"] == 0, **report})
            except asyncio.CancelledError:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                results.append({"node_id": node_id, "ok": False,
                                "error": f"{type(exc).__name__}:{str(exc)[:120]}"})
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
        print("TWINPANEL_NAIVE_FAST_AUTHENTICATED_PRESENCE_STARTED", flush=True)
        while True:
            started = time.monotonic()
            report = None
            try:
                report = await reconcile_once()
                print(json.dumps({"event": "naive_fast_presence", **report},
                                 separators=(",", ":")), flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(json.dumps({"event": "naive_fast_presence_crash",
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
