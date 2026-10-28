from __future__ import annotations

import asyncio
import fcntl
import json
import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_

from ..database import SessionLocal
from ..models import Node, NodeType
from ..node_runtime_connection import connect_protocol_runtime
from . import modern_quota_runtime_v257 as canonical


MODERN_ACCOUNTING_INTERVAL_SECONDS = canonical.MODERN_ACCOUNTING_INTERVAL_SECONDS
MODERN_ACCOUNTING_LOCK = canonical.MODERN_ACCOUNTING_LOCK


async def _collect_node_runtime(
    db,
    *,
    node: Node,
    grouped: dict[str, list[dict[str, Any]]],
) -> dict[str, tuple[Any, ...]]:
    """Collect node telemetry without holding accounting write transactions."""

    node_id = int(node.id)

    # build_node_devices() may backfill a canonical QuotaDevice. Persist that
    # compatibility work before any network await so a later rollback cannot
    # erase the mapping used by the collected telemetry.
    db.commit()

    node = db.get(Node, node_id)
    if node is None:
        raise RuntimeError(f"modern_accounting_node_missing:{node_id}")

    conn = None
    collected: dict[str, tuple[Any, ...]] = {}
    try:
        conn = await connect_protocol_runtime(node, db)

        # ssh_connect_saved() reads NodeAccess through this Session. End that
        # read transaction before the slower runtime probes. From this point
        # until connection shutdown there must be no accounting DB writes.
        db.commit()

        if grouped.get("wireguard"):
            collected["wireguard"] = await canonical._collect_wireguard_like(
                conn,
                binary="wg",
                interface="wg-access0",
            )

        if grouped.get("amneziawg"):
            collected["amneziawg"] = await canonical._collect_wireguard_like(
                conn,
                binary="awg",
                interface="tpawg0",
            )

        if grouped.get("trusttunnel"):
            collected["trusttunnel"] = await canonical._collect_trusttunnel(conn)

        if grouped.get("mieru"):
            collected["mieru"] = await canonical._collect_mieru(conn)

        if grouped.get("sudoku"):
            collected["sudoku"] = await canonical._collect_established_tcp_ports(conn)

        return collected
    finally:
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:
                pass


def _apply_collected_node_runtime(
    db,
    *,
    node_id: int,
    grouped: dict[str, list[dict[str, Any]]],
    collected: dict[str, tuple[Any, ...]],
) -> list[dict[str, Any]]:
    """Apply already-collected telemetry with no async/network boundary."""

    node = db.get(Node, int(node_id))
    if node is None:
        raise RuntimeError(f"modern_accounting_node_missing:{int(node_id)}")

    results: list[dict[str, Any]] = []

    if grouped.get("wireguard"):
        ok, epoch, peers, error = collected["wireguard"]
        results.append(
            {
                "ok": True,
                **canonical._apply_wireguard_like(
                    db,
                    node=node,
                    protocol="wireguard",
                    devices=grouped["wireguard"],
                    epoch=epoch,
                    peers=peers,
                    match_by_key=False,
                ),
            }
            if ok
            else {
                "ok": False,
                "collector": "wireguard",
                "node_id": int(node.id),
                "error": error or "wireguard_source_unavailable",
            }
        )

    if grouped.get("amneziawg"):
        ok, epoch, peers, error = collected["amneziawg"]
        results.append(
            {
                "ok": True,
                **canonical._apply_wireguard_like(
                    db,
                    node=node,
                    protocol="amneziawg",
                    devices=grouped["amneziawg"],
                    epoch=epoch,
                    peers=peers,
                    match_by_key=True,
                ),
            }
            if ok
            else {
                "ok": False,
                "collector": "amneziawg",
                "node_id": int(node.id),
                "error": error or "amneziawg_source_unavailable",
            }
        )

    if grouped.get("trusttunnel"):
        ok, epoch, rows, error = collected["trusttunnel"]
        results.append(
            {
                "ok": True,
                **canonical._apply_trusttunnel(
                    db,
                    node=node,
                    devices=grouped["trusttunnel"],
                    epoch=epoch,
                    rows=rows,
                ),
            }
            if ok
            else {
                "ok": False,
                "collector": "trusttunnel",
                "node_id": int(node.id),
                "error": error or "trusttunnel_source_unavailable",
            }
        )

    if grouped.get("mieru"):
        ok, rows, error = collected["mieru"]
        results.append(
            {
                "ok": True,
                **canonical._apply_mieru_presence(
                    db,
                    node=node,
                    devices=grouped["mieru"],
                    rows=rows,
                ),
            }
            if ok
            else {
                "ok": False,
                "collector": "mieru",
                "node_id": int(node.id),
                "error": error or "mieru_source_unavailable",
            }
        )

    if grouped.get("sudoku"):
        ok, ports, error = collected["sudoku"]
        results.append(
            {
                "ok": True,
                **canonical._apply_sudoku_presence(
                    db,
                    node=node,
                    devices=grouped["sudoku"],
                    established_ports=ports,
                ),
            }
            if ok
            else {
                "ok": False,
                "collector": "sudoku",
                "node_id": int(node.id),
                "error": error or "sudoku_source_unavailable",
            }
        )

    return results


async def _reconcile_node(db, node: Node) -> list[dict[str, Any]]:
    """Two-phase reconcile: all awaits first, then DB accounting writes."""

    node_id = int(node.id)
    grouped = canonical._devices_by_protocol(db, node_id)
    if not grouped:
        # End the read transaction opened while checking credentials/nodes.
        db.commit()
        return []

    collected = await _collect_node_runtime(
        db,
        node=node,
        grouped=grouped,
    )

    # IMPORTANT: there must be no await below this line. open_session() and
    # apply_usage_event() use row/advisory locks, so yielding after they start
    # can deadlock another synchronous collector task in this same event loop.
    return _apply_collected_node_runtime(
        db,
        node_id=node_id,
        grouped=grouped,
        collected=collected,
    )


async def reconcile_modern_quota_once() -> dict[str, Any]:
    db = SessionLocal()
    results: list[dict[str, Any]] = []
    try:
        node_ids = [
            int(row[0])
            for row in (
                db.query(Node.id)
                .filter(
                    Node.retired_at.is_(None),
                    or_(
                        Node.node_type == NodeType.EXIT,
                        Node.agent_url == "local://core",
                    ),
                )
                .order_by(Node.id.asc())
                .all()
            )
        ]
        # Do not carry the node-enumeration read transaction into SSH awaits.
        db.commit()

        for node_id in node_ids:
            try:
                node = db.get(Node, node_id)
                if node is None:
                    db.rollback()
                    results.append(
                        {
                            "ok": False,
                            "collector": "modern-runtime",
                            "node_id": node_id,
                            "error": "node_missing",
                        }
                    )
                    continue

                node_results = await _reconcile_node(db, node)
                # _reconcile_node guarantees no await after accounting writes.
                # Commit immediately after it returns to release row locks.
                db.commit()
                results.extend(node_results)
            except HTTPException as exc:
                db.rollback()
                results.append(
                    {
                        "ok": False,
                        "collector": "modern-runtime",
                        "node_id": node_id,
                        "error": f"http_{exc.status_code}:{str(exc.detail)[:500]}",
                    }
                )
            except Exception as exc:
                db.rollback()
                results.append(
                    {
                        "ok": False,
                        "collector": "modern-runtime",
                        "node_id": node_id,
                        "error": f"{type(exc).__name__}:{str(exc)[:500]}",
                    }
                )

        return {
            "ok": all(bool(item.get("ok")) for item in results) if results else True,
            "collectors": results,
        }
    finally:
        db.close()


async def modern_quota_runtime_loop() -> None:
    """Deadlock-safe V257 orchestration for the dedicated accounting worker."""

    MODERN_ACCOUNTING_LOCK.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = MODERN_ACCOUNTING_LOCK.open("a+")
    owns_lock = False
    try:
        while True:
            if not owns_lock:
                try:
                    fcntl.flock(
                        lock_handle.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                    owns_lock = True
                except BlockingIOError:
                    await asyncio.sleep(MODERN_ACCOUNTING_INTERVAL_SECONDS)
                    continue

            started = time.monotonic()
            try:
                result = await reconcile_modern_quota_once()
                if not bool(result.get("ok")):
                    print(
                        json.dumps(
                            {
                                "event": "modern_quota_reconcile",
                                "runtime": "v314",
                                **result,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        flush=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    json.dumps(
                        {
                            "event": "modern_quota_reconcile_crash",
                            "runtime": "v314",
                            "ok": False,
                            "error": f"{type(exc).__name__}:{str(exc)[:800]}",
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    flush=True,
                )

            delay = max(
                MODERN_ACCOUNTING_INTERVAL_SECONDS
                - (time.monotonic() - started),
                0.25,
            )
            await asyncio.sleep(delay)
    finally:
        if owns_lock:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        lock_handle.close()


capability_payload = canonical.capability_payload


__all__ = [
    "MODERN_ACCOUNTING_INTERVAL_SECONDS",
    "MODERN_ACCOUNTING_LOCK",
    "capability_payload",
    "modern_quota_runtime_loop",
    "reconcile_modern_quota_once",
]
