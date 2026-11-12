from __future__ import annotations

import asyncio
import fcntl
import json
import os
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
# When the dedicated subprocess owns Mieru sessions, exclude Mieru from
# heavyweight V314 sweeps to avoid duplicate writes and false offline closes.
# A missing independent-worker flag preserves the old collector for rollback.
MIERU_INDEPENDENT_WORKER = os.getenv("TP_MIERU_INDEPENDENT_WORKER", "") == "1"
SUDOKU_INDEPENDENT_WORKER = os.getenv("TP_SUDOKU_INDEPENDENT_WORKER", "") == "1"


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
        conn = await connect_protocol_runtime(
            node, db, close_read_transaction_before_ssh=True,
        )

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

        if grouped.get("mieru") and not MIERU_INDEPENDENT_WORKER:
            collected["mieru"] = await canonical._collect_mieru(conn)

        if grouped.get("sudoku") and not SUDOKU_INDEPENDENT_WORKER:
            collected["sudoku"] = await canonical._collect_established_tcp_ports(conn)

        return collected
    finally:
        if conn is not None:
            conn.close()
            try:
                await conn.wait_closed()
            except Exception:
                pass


# Avoid a single PostgreSQL write transaction spanning thousands of live
# devices. Each batch is committed before the next batch begins. Idempotent
# per-device quota cursors and canonical session keys remain unchanged.
ACCOUNTING_APPLY_BATCH_SIZE = 64


def _apply_collected_node_runtime_batched(
    db,
    *,
    node: Node,
    grouped: dict[str, list[dict[str, Any]]],
    collected: dict[str, tuple[Any, ...]],
) -> list[dict[str, Any]]:
    """Commit bounded, independently recoverable accounting batches.

    A partial failure preserves successful batches; the failed batch is rolled
    back to its savepoint and is retried using the existing per-device salvage.
    This function is synchronous: no network await occurs after any DB write.
    """
    node_id = int(node.id)
    outcomes: list[dict[str, Any]] = []

    for protocol in ("wireguard", "amneziawg", "trusttunnel", "mieru", "sudoku"):
        devices = grouped.get(protocol) or []
        if not devices:
            continue
        if protocol == "mieru" and MIERU_INDEPENDENT_WORKER:
            continue
        if protocol == "sudoku" and SUDOKU_INDEPENDENT_WORKER:
            continue

        reading = collected.get(protocol)
        if not reading or reading[0] is not True:
            outcomes.append({
                "ok": False,
                "collector": protocol,
                "node_id": node_id,
                "error": ((reading[-1] if reading else None) or f"{protocol}_source_unavailable"),
            })
            continue

        summary: dict[str, Any] = {
            "ok": True, "collector": protocol, "node_id": node_id,
        }
        failures: list[str] = []
        recovered = failed = 0

        for offset in range(0, len(devices), ACCOUNTING_APPLY_BATCH_SIZE):
            subset = devices[offset:offset + ACCOUNTING_APPLY_BATCH_SIZE]
            try:
                with db.begin_nested():
                    if protocol in ("wireguard", "amneziawg"):
                        _, epoch, peers, _ = reading
                        result = canonical._apply_wireguard_like(
                            db, node=node, protocol=protocol, devices=subset,
                            epoch=epoch, peers=peers,
                            match_by_key=protocol == "amneziawg",
                        )
                    elif protocol == "trusttunnel":
                        _, epoch, rows, _ = reading
                        result = canonical._apply_trusttunnel(
                            db, node=node, devices=subset, epoch=epoch, rows=rows,
                        )
                    elif protocol == "mieru":
                        _, rows, _ = reading
                        result = canonical._apply_mieru_presence(
                            db, node=node, devices=subset, rows=rows,
                        )
                    else:
                        _, ports, _ = reading
                        result = canonical._apply_sudoku_presence(
                            db, node=node, devices=subset, established_ports=ports,
                        )
                # Release row locks and the PostgreSQL transaction after
                # at most one bounded device batch; no await crosses a write.
                db.commit()
                for key, value in result.items():
                    if key not in ("collector", "node_id") and type(value) is int:
                        summary[key] = int(summary.get(key, 0)) + value
                    elif key not in ("collector", "node_id"):
                        summary[key] = value
            except Exception as exc:
                # begin_nested has already rolled this batch back. Reuse the
                # existing bounded per-device salvage for healthy identities.
                try:
                    salvage = _retry_failed_protocol_per_device(
                        db, node=node, protocol=protocol,
                        grouped={protocol: subset}, collected={protocol: reading},
                    )
                    recovered += int(salvage.get("recovered_devices") or 0)
                    failed += int(salvage.get("failed_devices") or 0)
                    db.commit()
                except Exception as salvage_exc:
                    db.rollback()
                    failed += len(subset)
                    failures.append(f"salvage:{type(salvage_exc).__name__}")
                failures.append(f"{type(exc).__name__}:{str(exc)[:160]}")

        if failures:
            summary.update({
                "ok": False,
                "error": "batch_apply_failed",
                "failed_batches": len(failures),
                "recovered_devices": recovered,
                "failed_devices": failed,
                "sample_errors": failures[:3],
            })
        outcomes.append(summary)

    return outcomes


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

    # Use bounded transactions only for large accounting sweeps; the small
    # canonical path remains byte-for-byte unchanged for existing deployments.
    if any(len(grouped.get(p) or ()) > ACCOUNTING_APPLY_BATCH_SIZE for p in (
        "wireguard", "amneziawg", "trusttunnel", "mieru", "sudoku",
    )):
        return _apply_collected_node_runtime_batched(
            db, node=node, grouped=grouped, collected=collected,
        )

    results: list[dict[str, Any]] = []

    if grouped.get("wireguard"):
        try:
            # Isolate this protocol's accounting without savepoint overhead
            # for protocols that have no devices on the current node.
            with db.begin_nested():
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
        except Exception as exc:
            recovery = _retry_failed_protocol_per_device(
                db, node=node, protocol="wireguard", grouped=grouped, collected=collected,
            )
            results.append({
                "ok": False, "collector": "wireguard", "node_id": int(node.id),
                "error": f"{type(exc).__name__}:{str(exc)[:350]}",
                **recovery,
            })

    if grouped.get("amneziawg"):
        try:
            # Isolate this protocol's accounting without savepoint overhead
            # for protocols that have no devices on the current node.
            with db.begin_nested():
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
        except Exception as exc:
            recovery = _retry_failed_protocol_per_device(
                db, node=node, protocol="amneziawg", grouped=grouped, collected=collected,
            )
            results.append({
                "ok": False, "collector": "amneziawg", "node_id": int(node.id),
                "error": f"{type(exc).__name__}:{str(exc)[:350]}",
                **recovery,
            })

    if grouped.get("trusttunnel"):
        try:
            # Isolate this protocol's accounting without savepoint overhead
            # for protocols that have no devices on the current node.
            with db.begin_nested():
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
        except Exception as exc:
            recovery = _retry_failed_protocol_per_device(
                db, node=node, protocol="trusttunnel", grouped=grouped, collected=collected,
            )
            results.append({
                "ok": False, "collector": "trusttunnel", "node_id": int(node.id),
                "error": f"{type(exc).__name__}:{str(exc)[:350]}",
                **recovery,
            })

    if grouped.get("mieru") and not MIERU_INDEPENDENT_WORKER:
        try:
            # Isolate this protocol's accounting without savepoint overhead
            # for protocols that have no devices on the current node.
            with db.begin_nested():
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
        except Exception as exc:
            recovery = _retry_failed_protocol_per_device(
                db, node=node, protocol="mieru", grouped=grouped, collected=collected,
            )
            results.append({
                "ok": False, "collector": "mieru", "node_id": int(node.id),
                "error": f"{type(exc).__name__}:{str(exc)[:350]}",
                **recovery,
            })

    if grouped.get("sudoku") and not SUDOKU_INDEPENDENT_WORKER:
        try:
            # Isolate this protocol's accounting without savepoint overhead
            # for protocols that have no devices on the current node.
            with db.begin_nested():
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
        except Exception as exc:
            recovery = _retry_failed_protocol_per_device(
                db, node=node, protocol="sudoku", grouped=grouped, collected=collected,
            )
            results.append({
                "ok": False, "collector": "sudoku", "node_id": int(node.id),
                "error": f"{type(exc).__name__}:{str(exc)[:350]}",
                **recovery,
            })

    return results


def _retry_failed_protocol_per_device(
    db,
    *,
    node: Node,
    protocol: str,
    grouped: dict[str, list[dict[str, Any]]],
    collected: dict[str, tuple[Any, ...]],
) -> dict[str, Any]:
    """Salvage healthy users after a node/protocol batch failed.

    The main batch has already rolled back to its savepoint. Retrying only
    after that error avoids thousands of savepoints during healthy sweeps.
    Never fabricate a connected session when telemetry is unavailable.
    """
    devices = grouped.get(protocol) or []
    reading = collected.get(protocol)
    if not reading or reading[0] is not True:
        return {"recovered_devices": 0, "failed_devices": len(devices)}
    recovered = 0
    failed = 0
    errors: list[str] = []
    # Avoid a storm of thousands of retry transactions on a busy VPN panel.
    # Rotate retry windows across sweeps so each affected user is eventually
    # revisited without starving ordinary accounting.
    retry_limit = 64
    windows = max((len(devices) + retry_limit - 1) // retry_limit, 1)
    window = int(time.time() // max(MODERN_ACCOUNTING_INTERVAL_SECONDS, 1)) % windows
    candidates = devices[window * retry_limit:(window + 1) * retry_limit]
    for device in candidates:
        try:
            with db.begin_nested():
                if protocol in {"wireguard", "amneziawg"}:
                    _, epoch, peers, _ = reading
                    canonical._apply_wireguard_like(
                        db, node=node, protocol=protocol, devices=[device],
                        epoch=epoch, peers=peers,
                        match_by_key=protocol == "amneziawg",
                    )
                elif protocol == "trusttunnel":
                    _, epoch, rows, _ = reading
                    canonical._apply_trusttunnel(
                        db, node=node, devices=[device], epoch=epoch, rows=rows,
                    )
                elif protocol == "mieru":
                    _, rows, _ = reading
                    canonical._apply_mieru_presence(
                        db, node=node, devices=[device], rows=rows,
                    )
                elif protocol == "sudoku":
                    _, ports, _ = reading
                    canonical._apply_sudoku_presence(
                        db, node=node, devices=[device], established_ports=ports,
                    )
                else:
                    raise RuntimeError("unsupported_protocol_salvage")
            recovered += 1
        except Exception as exc:
            failed += 1
            if len(errors) < 3:
                errors.append(f"{type(exc).__name__}:{str(exc)[:120]}")
    return {
        "recovered_devices": recovered,
        "failed_devices": failed,
        "deferred_devices": len(devices) - len(candidates),
        "sample_errors": errors,
    }


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
    # The fresh dedicated worker session has no pending billing writes before
    # its first credential/device-map cache build.
    db.info["twinpanel_v314_clean_lookup_session"] = True
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
            result = None
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

            # Avoid a CPU/DB hot-loop when a full fleet collection takes
            # longer than the nominal 45-second accounting interval.
            # Errors back off longer; source-unavailable is not zero traffic.
            min_rest = 15.0 if result is None or not result.get("ok", False) else 5.0
            delay = max(
                MODERN_ACCOUNTING_INTERVAL_SECONDS - (time.monotonic() - started),
                min_rest,
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
