from __future__ import annotations

import asyncio
import ast
import fcntl
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Tunnel, TunnelTransport
from .transport_candidates import tp27_fast
from .transport_candidates.common import (
    close_pair,
    connect_pair,
    mark,
    prerequisites,
    probe,
    runtime,
    tunnel_nodes,
)


# ============================================================
# TWINPANEL TP27 SELF REPAIR V265
#
# TP27 Fast is a logical SmartAuto/manual transport whose carrier is a Linux
# keyed-GRE interface (native protocol 47) with GRE-in-UDP/FoU fallback.
# The carrier service is intentionally oneshot/RemainAfterExit, therefore
# systemd being active is not sufficient proof that the L3 peer is reachable.
#
# V265 owns *carrier* repair only:
#   * observe the real TP27 /30 in both directions;
#   * require consecutive failures before autonomous mutation;
#   * serialize API/manual and background repair across processes;
#   * preserve manual-vs-auto transport policy;
#   * never switch the logical transport to another candidate;
#   * when native GRE becomes unstable after installation, prefer FoU during
#     repair instead of repeatedly selecting the briefly-working native path;
#   * verify every rebuilt profile with the full TP27 dataplane probe;
#   * persist repair telemetry inside TunnelTransport.config_text.
# ============================================================

MARKER = "TWINPANEL_TP27_SELF_REPAIR_V265"
LOOP_SECONDS = 30
FAILURE_THRESHOLD = 3
REPAIR_COOLDOWN_SECONDS = 180

_failure_cycles: dict[int, int] = {}


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _meta(raw: str | None) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    try:
        value = ast.literal_eval(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {}


def _tp27_row(db: Session, tunnel_id: int) -> TunnelTransport | None:
    return (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == "tp27_fast",
        )
        .first()
    )


@asynccontextmanager
async def _repair_lock(tunnel_id: int):
    """Serialize TP27 rebuilds across API workers and the manager process."""

    path = Path(f"/tmp/twinpanel-tp27-repair-{int(tunnel_id)}.lock")
    handle = path.open("a+")
    try:
        await asyncio.to_thread(fcntl.flock, handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            await asyncio.to_thread(fcntl.flock, handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


async def _peer_snapshot(conn, *, service: str, interface: str, peer_ip: str) -> dict:
    service_result, link_result, addr_result, ping_result = await asyncio.gather(
        conn.run(
            f"systemctl is-active {service}",
            check=False,
            timeout=15,
        ),
        conn.run(
            f"ip -o link show dev {interface}",
            check=False,
            timeout=15,
        ),
        conn.run(
            f"ip -4 -o addr show dev {interface}",
            check=False,
            timeout=15,
        ),
        conn.run(
            f"LC_ALL=C ping -I {interface} -c 3 -W 2 {peer_ip}",
            check=False,
            timeout=15,
        ),
    )

    service_state = str(service_result.stdout or "").strip().lower()
    link_text = str(link_result.stdout or "").strip()
    addr_text = str(addr_result.stdout or "").strip()
    ping_text = str(ping_result.stdout or "").strip()

    return {
        "service_active": service_result.exit_status == 0 and service_state == "active",
        "service_state": service_state or "unknown",
        "interface_present": link_result.exit_status == 0 and bool(link_text),
        "address_present": addr_result.exit_status == 0 and bool(addr_text),
        "peer_reachable": ping_result.exit_status == 0,
        "ping_summary": ping_text.splitlines()[-1] if ping_text else "",
    }


async def _diagnose_with_connections(ci, ce, rt: dict[str, Any]) -> dict:
    iran, exit_side = await asyncio.gather(
        _peer_snapshot(
            ci,
            service=str(rt["iran_service"]),
            interface=str(rt["interface"]),
            peer_ip=str(rt["exit_ip"]),
        ),
        _peer_snapshot(
            ce,
            service=str(rt["exit_service"]),
            interface=str(rt["interface"]),
            peer_ip=str(rt["iran_ip"]),
        ),
    )

    healthy = bool(
        iran["service_active"]
        and exit_side["service_active"]
        and iran["interface_present"]
        and exit_side["interface_present"]
        and iran["address_present"]
        and exit_side["address_present"]
        and iran["peer_reachable"]
        and exit_side["peer_reachable"]
    )

    return {
        "healthy": healthy,
        "interface": rt["interface"],
        "network": rt["network"],
        "iran_ip": rt["iran_ip"],
        "exit_ip": rt["exit_ip"],
        "iran": iran,
        "exit": exit_side,
    }


async def diagnose_tp27(tunnel_id: int, db: Session) -> dict:
    """Read-only carrier diagnosis. No interface, firewall or route mutation."""

    tunnel, iran, exit_node = tunnel_nodes(db, int(tunnel_id))
    row = _tp27_row(db, int(tunnel_id))
    if row is None:
        raise RuntimeError("tp27_not_installed")

    rt = runtime("tp27_fast", int(tunnel_id))
    cfg = _meta(row.config_text)
    ci = ce = None

    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        carrier = await _diagnose_with_connections(ci, ce, rt)
        return {
            "ok": True,
            "marker": MARKER,
            "tunnel_id": int(tunnel.id),
            "mode": str(tunnel.mode or "manual"),
            "active_transport": tunnel.active_transport,
            "preferred_transport": tunnel.preferred_transport,
            "transport_status": _status(row.status),
            "last_error": row.last_error,
            "selected_profile": cfg.get("selected_profile"),
            "fou_port": cfg.get("fou_port"),
            "repair_state": cfg.get("tp27_self_repair_v265") or {},
            "carrier": carrier,
            "healthy": bool(carrier["healthy"]),
        }
    finally:
        await close_pair(ci, ce)


def _attempt_order(cfg: dict[str, Any]) -> list[tuple[str, int | None]]:
    """Prefer a different carrier family after a runtime failure.

    Initial install remains native-first in tp27_fast.install(). Repair is
    intentionally different: if native GRE passed installation but later
    became unreachable, try FoU first so a transient protocol-47 success does
    not create an endless native-GRE failure loop.
    """

    current = str(cfg.get("selected_profile") or "").strip().lower()
    current_port = 0
    try:
        current_port = int(cfg.get("fou_port") or 0)
    except (TypeError, ValueError):
        current_port = 0

    ports = [int(value) for value in tp27_fast.FOU_PORT_CANDIDATES]
    if current == "gre-fou" and current_port in ports:
        ports = [current_port] + [value for value in ports if value != current_port]

    fou = [("gre-fou", value) for value in ports]
    if current == "gre-native":
        return fou + [("gre-native", None)]
    if current == "gre-fou":
        return fou + [("gre-native", None)]
    return [("gre-native", None)] + fou


def _repair_meta(
    existing: dict[str, Any],
    *,
    rt: dict[str, Any],
    profile: str,
    fou_port: int | None,
    health: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    now = datetime.utcnow()
    out = dict(existing)
    out.update(rt)
    out.update(health)
    out.update(
        {
            "source": "matin111/tp27-core",
            "selected_profile": profile,
            "gre_key": existing.get("gre_key"),
            "mtu": tp27_fast.MTU,
            "repair_attempts": attempts,
            "tp27_self_repair_v265": {
                "version": 265,
                "last_repair_at": now.isoformat() + "Z",
                "last_repair_epoch": now.timestamp(),
                "last_result": "online",
                "selected_profile": profile,
                "fou_port": fou_port,
            },
        }
    )
    if fou_port is None:
        out.pop("fou_port", None)
    else:
        out["fou_port"] = int(fou_port)
    return out


async def _repair_tp27_locked(
    tunnel_id: int,
    db: Session,
    *,
    force_rebuild: bool,
    source: str,
) -> dict:
    tunnel, iran, exit_node = tunnel_nodes(db, int(tunnel_id))
    row = _tp27_row(db, int(tunnel_id))
    if row is None:
        raise RuntimeError("tp27_not_installed")
    if not bool(row.enabled):
        raise RuntimeError("tp27_disabled")

    original_mode = str(tunnel.mode or "manual")
    original_active = tunnel.active_transport
    original_preferred = tunnel.preferred_transport
    rt = runtime("tp27_fast", int(tunnel_id))
    cfg = _meta(row.config_text)
    gre_key = tp27_fast._gre_key(
        int(tunnel_id),
        str(iran.public_ip),
        str(exit_node.public_ip),
    )
    ci = ce = None
    attempts: list[dict[str, Any]] = []

    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))

        before = await _diagnose_with_connections(ci, ce, rt)
        if bool(before["healthy"]) and not force_rebuild:
            row.status = "online"
            row.last_error = None
            row.last_healthy_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()
            db.commit()
            return {
                "ok": True,
                "marker": MARKER,
                "tunnel_id": int(tunnel_id),
                "source": source,
                "changed": False,
                "reason": "carrier_already_healthy",
                "mode_preserved": original_mode,
                "active_transport_preserved": original_active,
                "preferred_transport_preserved": original_preferred,
                "before": before,
                "after": before,
            }

        for profile, fou_port in _attempt_order(cfg):
            attempt: dict[str, Any] = {
                "profile": profile,
                "fou_port": fou_port,
            }
            try:
                await tp27_fast._install_profile(
                    ci,
                    ce,
                    tunnel_id=int(tunnel_id),
                    iran_public=str(iran.public_ip),
                    exit_public=str(exit_node.public_ip),
                    rt=rt,
                    gre_key=gre_key,
                    profile=profile,
                    fou_port=fou_port,
                )
                health = await probe(
                    ci,
                    ce,
                    name="tp27_fast",
                    tunnel_id=int(tunnel_id),
                    rt=rt,
                )
                attempt["result"] = "online"
                attempts.append(attempt)

                meta = _repair_meta(
                    cfg,
                    rt=rt,
                    profile=profile,
                    fou_port=fou_port,
                    health=health,
                    attempts=attempts,
                )
                mark(
                    db,
                    int(tunnel_id),
                    "tp27_fast",
                    status="online",
                    latency_ms=health.get("latency_ms"),
                    meta=json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
                )

                # Carrier repair must never rewrite the user's transport policy.
                db.expire_all()
                live = db.get(Tunnel, int(tunnel_id))
                if live is not None:
                    live.mode = original_mode
                    live.active_transport = original_active
                    live.preferred_transport = original_preferred
                    db.commit()

                after = await _diagnose_with_connections(ci, ce, rt)
                if not bool(after["healthy"]):
                    raise RuntimeError("post_repair_carrier_probe_failed")

                return {
                    "ok": True,
                    "marker": MARKER,
                    "tunnel_id": int(tunnel_id),
                    "source": source,
                    "changed": True,
                    "profile": profile,
                    "fou_port": fou_port,
                    "mode_preserved": original_mode,
                    "active_transport_preserved": original_active,
                    "preferred_transport_preserved": original_preferred,
                    "before": before,
                    "after": after,
                    "dataplane_probe": health,
                    "attempts": attempts,
                }
            except Exception as exc:
                attempt["result"] = "failed"
                attempt["error"] = f"{type(exc).__name__}:{exc}"[:1200]
                attempts.append(attempt)

        await tp27_fast._reset_pair(ci, ce, rt)
        message = "tp27_repair_all_profiles_failed:" + json.dumps(
            attempts,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        failed_meta = dict(cfg)
        failed_meta["tp27_self_repair_v265"] = {
            "version": 265,
            "last_repair_at": datetime.utcnow().isoformat() + "Z",
            "last_repair_epoch": datetime.utcnow().timestamp(),
            "last_result": "failed",
            "source": source,
            "attempts": attempts[-8:],
        }
        mark(
            db,
            int(tunnel_id),
            "tp27_fast",
            status="failed",
            error=message,
            meta=json.dumps(failed_meta, ensure_ascii=False, separators=(",", ":")),
        )
        raise RuntimeError(message)

    finally:
        # Explicitly preserve the logical policy even if a future helper starts
        # writing Tunnel fields as part of candidate installation.
        try:
            db.expire_all()
            live = db.get(Tunnel, int(tunnel_id))
            if live is not None:
                live.mode = original_mode
                live.active_transport = original_active
                live.preferred_transport = original_preferred
                db.commit()
        except Exception:
            db.rollback()
        await close_pair(ci, ce)


async def repair_tp27(
    tunnel_id: int,
    db: Session,
    *,
    force_rebuild: bool = False,
    source: str = "api",
) -> dict:
    async with _repair_lock(int(tunnel_id)):
        return await _repair_tp27_locked(
            int(tunnel_id),
            db,
            force_rebuild=bool(force_rebuild),
            source=str(source or "api"),
        )


def _candidate_tunnel_ids() -> list[int]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Tunnel.id)
            .join(
                TunnelTransport,
                TunnelTransport.tunnel_id == Tunnel.id,
            )
            .filter(
                Tunnel.is_active.is_(True),
                TunnelTransport.transport == "tp27_fast",
                TunnelTransport.enabled.is_(True),
            )
            .order_by(Tunnel.id.asc())
            .all()
        )
        return [int(row[0]) for row in rows]
    finally:
        db.close()


def _cooldown_remaining(row: TunnelTransport | None) -> int:
    if row is None:
        return 0
    state = _meta(row.config_text).get("tp27_self_repair_v265")
    if not isinstance(state, dict):
        return 0
    try:
        last = float(state.get("last_repair_epoch") or 0.0)
    except (TypeError, ValueError):
        return 0
    elapsed = max(0.0, datetime.utcnow().timestamp() - last)
    return max(0, int(REPAIR_COOLDOWN_SECONDS - elapsed))


async def reconcile_once() -> dict:
    checked: list[int] = []
    repaired: list[int] = []
    failed: dict[int, str] = {}

    for tunnel_id in _candidate_tunnel_ids():
        checked.append(int(tunnel_id))
        db = SessionLocal()
        try:
            tunnel = db.get(Tunnel, int(tunnel_id))
            row = _tp27_row(db, int(tunnel_id))
            if tunnel is None or row is None:
                _failure_cycles.pop(int(tunnel_id), None)
                continue

            # Do not rebuild a healthy standby TP27 lane merely because some
            # other logical transport is currently selected. We still observe
            # it so a preferred/manual TP27 carrier can recover automatically.
            selected = str(tunnel.active_transport or "").strip().lower()
            preferred = str(tunnel.preferred_transport or "").strip().lower()
            mode = str(tunnel.mode or "manual").strip().lower()
            relevant = bool(
                selected == "tp27_fast"
                or preferred == "tp27_fast"
                or _status(row.status) in {"offline", "failed", "degraded"}
                or mode == "manual"
            )
            if not relevant:
                _failure_cycles.pop(int(tunnel_id), None)
                continue

            try:
                diagnosis = await diagnose_tp27(int(tunnel_id), db)
            except Exception as exc:
                diagnosis = {
                    "healthy": False,
                    "error": f"{type(exc).__name__}:{exc}",
                }

            if bool(diagnosis.get("healthy")):
                _failure_cycles[int(tunnel_id)] = 0
                if _status(row.status) != "online":
                    row.status = "online"
                    row.last_error = None
                    row.last_healthy_at = datetime.utcnow()
                    row.updated_at = datetime.utcnow()
                    db.commit()
                continue

            count = _failure_cycles.get(int(tunnel_id), 0) + 1
            _failure_cycles[int(tunnel_id)] = count
            print(
                f"{MARKER}_UNREACHABLE tunnel={int(tunnel_id)} "
                f"count={count}/{FAILURE_THRESHOLD} "
                f"mode={mode} active={selected or 'none'}",
                flush=True,
            )

            if count < FAILURE_THRESHOLD:
                continue

            remaining = _cooldown_remaining(row)
            if remaining > 0:
                print(
                    f"{MARKER}_COOLDOWN tunnel={int(tunnel_id)} "
                    f"remaining={remaining}s",
                    flush=True,
                )
                continue

            try:
                result = await repair_tp27(
                    int(tunnel_id),
                    db,
                    force_rebuild=True,
                    source="manager",
                )
                if bool(result.get("ok")):
                    repaired.append(int(tunnel_id))
                    _failure_cycles[int(tunnel_id)] = 0
                    print(
                        f"{MARKER}_RECOVERED tunnel={int(tunnel_id)} "
                        f"profile={result.get('profile')} "
                        f"fou_port={result.get('fou_port')}",
                        flush=True,
                    )
            except Exception as exc:
                db.rollback()
                failed[int(tunnel_id)] = f"{type(exc).__name__}:{exc}"[:1800]
                _failure_cycles[int(tunnel_id)] = 0
                print(
                    f"{MARKER}_REPAIR_FAILED tunnel={int(tunnel_id)} "
                    f"error={failed[int(tunnel_id)]!r}",
                    flush=True,
                )
        finally:
            db.close()

    return {
        "checked": checked,
        "repaired": repaired,
        "failed": failed,
        "marker": MARKER,
    }


async def reconciler_loop() -> None:
    print(
        f"{MARKER}_START interval={LOOP_SECONDS}s "
        f"failure_threshold={FAILURE_THRESHOLD} "
        f"cooldown={REPAIR_COOLDOWN_SECONDS}s",
        flush=True,
    )

    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                f"{MARKER}_ERROR {type(exc).__name__}:{exc}",
                flush=True,
            )
        await asyncio.sleep(LOOP_SECONDS)
