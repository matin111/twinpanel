from __future__ import annotations

import ast
import asyncio
import json
import math
import os
import re
import shlex
import time
from datetime import datetime

from . import transport_policy_v17 as v17
from . import tunnel_transport_manager_v7 as v7
from . import tunnel_transport_manager_v8 as v8
from .database import SessionLocal
from .models import Node, Tunnel, TunnelStatus, TunnelTransport
from .routers.provision import ssh_connect_saved
from .transport_candidates import SPECS, install_transport
from .transport_candidates.common import (
    close_pair,
    connect_pair,
    probe as candidate_probe,
    runtime as candidate_runtime,
)

# ============================================================
# TWINPANEL SMART IRAN TRANSPORT AUTO V21
#
# Candidate lifecycle:
#   discover -> install -> full dataplane probe -> 60s stability ->
#   bounded bidirectional throughput benchmark -> score -> promote
#
# Selection goals:
#   * health is a hard gate
#   * download matters more than upload (70/30)
#   * packet loss / restarts / latency are penalized
#   * broken candidates are quarantined instead of deleted
#   * manual mode is never overridden
#   * one install and one benchmark run globally at a time
#
# QUIC 0.6.1-frag is intentionally auto-blocked. Production A/B
# showed working lanes=1 throughput but broken lanes=8 dataplane and
# idle-timeout process exits. Manual rollback remains available.
# ============================================================

CANDIDATE_NAMES = frozenset(SPECS)
AUTO_INSTALL_NAMES = ("kernel_gre", "gost_tun", "amneziawg", "netrix")

BASE_MODERN_NAMES = frozenset(
    {"kcp_2027", "arq_2027", "quic_2027", "tcp_2027"}
)
LEGACY_NAMES = frozenset(
    {"backhaul", "mtunnel", "ssh_tun", "ssh_relay"}
)
ALL_AUTO_NAMES = frozenset(
    BASE_MODERN_NAMES | CANDIDATE_NAMES | LEGACY_NAMES
)

MAX_PACKET_LOSS_PCT = 5.0
CANDIDATE_STABLE_SECONDS = 60.0
ACTIVE_FAILURE_THRESHOLD = 2
PROMOTION_HOLD_SECONDS = 30.0
MIN_DWELL_SECONDS = 90.0
MIN_SPEED_GAIN_MBPS = 2.0
MIN_SPEED_GAIN_RATIO = 0.15
MIN_UNMEASURED_PROMOTION_MBPS = 10.0

HEALTH_CACHE_SECONDS = 20.0
INSTALL_RETRY_SECONDS = 1800.0

BENCHMARK_SECONDS = 3.0
BENCHMARK_MAX_BYTES = 64 * 1024 * 1024
BENCHMARK_STREAMS = 4
BENCHMARK_SCHEDULE_SECONDS = 25.0
BENCHMARK_REFRESH_SECONDS = 600.0
BENCHMARK_SAMPLE_TTL_SECONDS = 1800.0

_BASE_OVERLAY_HEALTH = None

_candidate_health_cache: dict[tuple[int, str], tuple[float, dict]] = {}
_candidate_target: dict[int, str | None] = {}
_candidate_since: dict[int, float | None] = {}
_failure_count: dict[int, int] = {}
_last_install_started: dict[int, float] = {}
_last_benchmark_started: dict[int, float] = {}

_install_task: asyncio.Task | None = None
_benchmark_task: asyncio.Task | None = None


RECEIVER_CODE = r"""
import socket,sys,threading,time
ip=sys.argv[1]
port=int(sys.argv[2])
streams=max(1,int(sys.argv[3]))
listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
listener.bind((ip,port))
listener.listen(streams)
listener.settimeout(8)
print("READY",flush=True)
lock=threading.Lock()
total=0
first=None
last=None

def worker(conn):
    global total,first,last
    conn.settimeout(1)
    deadline=time.monotonic()+8
    local=0
    local_first=None
    local_last=None
    try:
        while time.monotonic()<deadline:
            try:
                data=conn.recv(262144)
            except socket.timeout:
                continue
            if not data:
                break
            now=time.monotonic()
            if local_first is None:
                local_first=now
            local_last=now
            local+=len(data)
    finally:
        try: conn.close()
        except Exception: pass
    with lock:
        total+=local
        if local_first is not None and (first is None or local_first<first):
            first=local_first
        if local_last is not None and (last is None or local_last>last):
            last=local_last

threads=[]
try:
    for _ in range(streams):
        conn,_=listener.accept()
        t=threading.Thread(target=worker,args=(conn,),daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(9)
finally:
    try: listener.close()
    except Exception: pass

elapsed=max((last-first) if first is not None and last is not None else 0.001,0.001)
print(f"RX_BYTES={total}",flush=True)
print(f"RX_SECONDS={elapsed:.6f}",flush=True)
print(f"RX_MBPS={total*8.0/elapsed/1000000.0:.3f}",flush=True)
"""

SENDER_CODE = r"""
import socket,sys,threading,time
src=sys.argv[1]
dst=sys.argv[2]
port=int(sys.argv[3])
seconds=float(sys.argv[4])
max_bytes=int(sys.argv[5])
streams=max(1,int(sys.argv[6]))
per_stream=max(1,max_bytes//streams)
barrier=threading.Barrier(streams)
lock=threading.Lock()
total=0
first=None
last=None
payload=b"x"*262144

def worker():
    global total,first,last
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.settimeout(3)
    s.bind((src,0))
    s.connect((dst,port))
    barrier.wait()
    start=time.monotonic()
    deadline=start+seconds
    local=0
    try:
        while time.monotonic()<deadline and local<per_stream:
            chunk=payload[:min(len(payload),per_stream-local)]
            try:
                sent=s.send(chunk)
            except socket.timeout:
                continue
            if sent<=0:
                break
            local+=sent
    finally:
        try: s.shutdown(socket.SHUT_WR)
        except Exception: pass
        try: s.close()
        except Exception: pass
    end=time.monotonic()
    with lock:
        total+=local
        if first is None or start<first:
            first=start
        if last is None or end>last:
            last=end

threads=[threading.Thread(target=worker,daemon=True) for _ in range(streams)]
for t in threads: t.start()
for t in threads: t.join(seconds+6)
elapsed=max((last-first) if first is not None and last is not None else 0.001,0.001)
print(f"TX_BYTES={total}",flush=True)
print(f"TX_SECONDS={elapsed:.6f}",flush=True)
print(f"TX_MBPS={total*8.0/elapsed/1000000.0:.3f}",flush=True)
"""


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _safe_float(value: object, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        result = float(value)
        if not math.isfinite(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _config(row: TunnelTransport | None) -> dict:
    if row is None or not row.config_text:
        return {}
    raw = str(row.config_text)
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    # Early canary installers stored Python repr(dict). Accept and normalize it
    # when we next write telemetry, without executing arbitrary code.
    try:
        value = ast.literal_eval(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {}


def _write_config(row: TunnelTransport, cfg: dict) -> None:
    row.config_text = json.dumps(
        cfg,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _smart_state(row: TunnelTransport | None) -> dict:
    value = _config(row).get("smart_auto_v21")
    return value if isinstance(value, dict) else {}


def _set_smart_state(
    row: TunnelTransport,
    *,
    merge: dict | None = None,
) -> dict:
    cfg = _config(row)
    state = cfg.get("smart_auto_v21")
    if not isinstance(state, dict):
        state = {}
    if merge:
        state.update(merge)
    cfg["smart_auto_v21"] = state
    _write_config(row, cfg)
    return state


def _quic_version(row: TunnelTransport) -> str:
    cfg = _config(row)
    state = cfg.get("smart_auto_v21")
    if not isinstance(state, dict):
        state = {}
    return str(
        cfg.get("version")
        or cfg.get("artifact_version")
        or state.get("version")
        or ""
    ).strip().lower()


def auto_block_reason(row: TunnelTransport) -> str | None:
    name = _name(row.transport)

    if name == "quic_2027":
        version = _quic_version(row)
        # Current production artifact is 0.6.1-frag. Rows from older installs
        # may not persist version metadata, so unknown legacy QUIC is blocked
        # until a validated replacement artifact explicitly reports a new version.
        if not version or version == "0.6.1-frag":
            return "known_bad_quic_0.6.1_frag_dataplane_idle_timeout"

    state = _smart_state(row)
    until = _safe_float(state.get("quarantine_until_epoch"), 0.0) or 0.0
    if until > time.time():
        return str(state.get("quarantine_reason") or "quarantined")

    return None


def _candidate_rt(name: str, tunnel_id: int) -> dict:
    return candidate_runtime(_name(name), int(tunnel_id))


def _benchmark_meta(row: TunnelTransport, tunnel_id: int) -> dict | None:
    name = _name(row.transport)

    if name in CANDIDATE_NAMES:
        rt = _candidate_rt(name, tunnel_id)
        return {
            "transport": name,
            "interface": str(rt["interface"]),
            "iran_ip": str(rt["iran_ip"]).split("/", 1)[0],
            "exit_ip": str(rt["exit_ip"]).split("/", 1)[0],
        }

    cfg = _config(row)
    interface = str(cfg.get("interface") or "").strip()
    iran_ip = str(cfg.get("iran_ip") or "").strip().split("/", 1)[0]
    exit_ip = str(cfg.get("exit_ip") or "").strip().split("/", 1)[0]

    if name in BASE_MODERN_NAMES and not (interface and iran_ip and exit_ip):
        try:
            from .tp2027_provision import tp2027_runtime_values

            rt = tp2027_runtime_values(name, int(tunnel_id))
            interface = str(rt.get("interface") or "").strip()
            iran_ip = str(rt.get("iran_ip") or "").strip()
            exit_ip = str(rt.get("exit_ip") or "").strip()
        except Exception:
            pass

    if name == "backhaul" and not (interface and iran_ip and exit_ip):
        try:
            from .tp2027_provision import backhaul_runtime_values

            rt = backhaul_runtime_values(int(tunnel_id))
            interface = str(rt.get("interface") or "").strip()
            iran_ip = str(rt.get("iran_ip") or "").strip()
            exit_ip = str(rt.get("exit_ip") or "").strip()
        except Exception:
            pass

    if name == "mtunnel" and not (interface and iran_ip and exit_ip):
        try:
            from .mtunnel_transport import mtunnel_runtime_values

            rt = mtunnel_runtime_values(int(tunnel_id))
            interface = str(rt.get("interface") or "").strip()
            iran_ip = str(rt.get("iran_ip") or "").strip()
            exit_ip = str(rt.get("exit_ip") or "").strip()
        except Exception:
            pass

    if not (interface and iran_ip and exit_ip):
        return None

    return {
        "transport": name,
        "interface": interface,
        "iran_ip": iran_ip,
        "exit_ip": exit_ip,
    }


def _throughput_sample(
    row: TunnelTransport,
    now_epoch: float | None = None,
) -> dict | None:
    state = _smart_state(row)
    data = state.get("throughput")
    if not isinstance(data, dict):
        return None

    try:
        measured = float(data["measured_at_epoch"])
        down = float(data["download_mbps"])
        up = float(data["upload_mbps"])
        weighted = float(data["weighted_mbps"])
    except (KeyError, TypeError, ValueError):
        return None

    if not all(math.isfinite(v) and v > 0 for v in (measured, down, up, weighted)):
        return None

    now = time.time() if now_epoch is None else float(now_epoch)
    age = max(0.0, now - measured)
    if age > BENCHMARK_SAMPLE_TTL_SECONDS:
        return None

    return {
        "measured_at_epoch": measured,
        "download_mbps": down,
        "upload_mbps": up,
        "weighted_mbps": weighted,
        "age_seconds": age,
    }


def _health_seed(row: TunnelTransport) -> dict | None:
    if _status(row.status) != "online":
        return None
    if row.latency_ms is None or row.last_healthy_at is None:
        return None

    try:
        stamp = row.last_healthy_at
        if getattr(stamp, "tzinfo", None) is not None:
            stamp = stamp.replace(tzinfo=None)
        age = max(0.0, (datetime.utcnow() - stamp).total_seconds())
    except Exception:
        return None

    if age > 90.0:
        return None

    return {
        "ok": True,
        "latency_ms": int(row.latency_ms),
        "packet_loss_pct": None,
        "error": None,
        "telemetry_source": "recent_db_seed",
    }


def _candidate_auto_eligible(row: TunnelTransport, health: dict | None) -> bool:
    if auto_block_reason(row):
        return False
    if not health or not bool(health.get("ok")):
        return False

    loss = _safe_float(health.get("packet_loss_pct"), 0.0) or 0.0
    if loss > MAX_PACKET_LOSS_PCT:
        return False

    if _name(row.transport) in CANDIDATE_NAMES:
        stable_seconds = _safe_float(
            _smart_state(row).get("stable_seconds"),
            0.0,
        ) or 0.0
        if stable_seconds < CANDIDATE_STABLE_SECONDS:
            return False

    return True


def _quality_score(
    row: TunnelTransport,
    health: dict,
) -> float:
    # Lower is better. Throughput dominates, but health quality still matters.
    sample = _throughput_sample(row)
    latency = _safe_float(health.get("latency_ms"), 500.0) or 500.0
    loss = _safe_float(health.get("packet_loss_pct"), 1.0)
    if loss is None:
        loss = 1.0

    if sample is None:
        speed_penalty = 75.0
    else:
        # Weighted speed = 70% download + 30% upload. Cap benefit to prevent
        # one very large synthetic number from masking loss/restart problems.
        speed = min(float(sample["weighted_mbps"]), 200.0)
        speed_penalty = max(0.0, 100.0 - speed)

    restart_penalty = 0.0
    if _name(row.transport) in CANDIDATE_NAMES:
        restarts = _safe_float(health.get("restart_count"), 0.0) or 0.0
        restart_penalty = min(30.0, restarts * 5.0)

    return (
        speed_penalty
        + min(40.0, max(0.0, latency) / 20.0)
        + min(50.0, max(0.0, loss) * 5.0)
        + restart_penalty
    )


def _ranked(
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> list[tuple[str, float]]:
    ranked: list[tuple[str, float, int, int]] = []

    for row in rows:
        name = _name(row.transport)
        result = health.get(name)

        if name not in ALL_AUTO_NAMES:
            continue
        if not bool(row.enabled):
            continue
        if not _candidate_auto_eligible(row, result):
            continue

        ranked.append(
            (
                name,
                _quality_score(row, result),
                int(row.priority or 10**9),
                int(row.id or 0),
            )
        )

    ranked.sort(key=lambda item: (item[1], item[2], item[3], item[0]))
    return [(name, score) for name, score, _p, _id in ranked]


def _materially_faster(
    best_row: TunnelTransport,
    active_row: TunnelTransport | None,
) -> bool:
    best = _throughput_sample(best_row)
    if best is None:
        return False

    if active_row is None:
        return float(best["weighted_mbps"]) >= MIN_UNMEASURED_PROMOTION_MBPS

    active = _throughput_sample(active_row)
    if active is None:
        return float(best["weighted_mbps"]) >= MIN_UNMEASURED_PROMOTION_MBPS

    best_speed = float(best["weighted_mbps"])
    active_speed = float(active["weighted_mbps"])
    absolute = best_speed - active_speed
    ratio = absolute / max(active_speed, 0.1)

    return (
        absolute >= MIN_SPEED_GAIN_MBPS
        and ratio >= MIN_SPEED_GAIN_RATIO
    )


def _reset_candidate(tunnel_id: int) -> None:
    tid = int(tunnel_id)
    _candidate_target[tid] = None
    _candidate_since[tid] = None


def _dwell_seconds(tunnel: Tunnel) -> float:
    stamp = getattr(tunnel, "last_switch_at", None)
    if stamp is None:
        return math.inf
    try:
        if getattr(stamp, "tzinfo", None) is not None:
            stamp = stamp.replace(tzinfo=None)
        return max(0.0, (datetime.utcnow() - stamp).total_seconds())
    except Exception:
        return math.inf


def managed_tunnel_ids_v21(
    only_tunnel: int | None = None,
) -> list[int]:
    db = SessionLocal()
    try:
        query = (
            db.query(Tunnel.id)
            .filter(
                Tunnel.is_active.is_(True),
                Tunnel.mode == "auto",
            )
            .order_by(Tunnel.id.asc())
        )
        if only_tunnel is not None:
            query = query.filter(Tunnel.id == int(only_tunnel))
        return [int(row[0]) for row in query.all()]
    finally:
        db.close()


def _netrix_available() -> bool:
    try:
        from .transport_candidates.netrix import _binary

        _binary()
        return True
    except Exception:
        return False


def _install_candidate_name(
    tunnel_id: int,
) -> str | None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        for name in AUTO_INSTALL_NAMES:
            if name == "netrix" and not _netrix_available():
                continue

            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == name,
                )
                .first()
            )

            if row is None:
                return name

            if bool(row.enabled) and _status(row.status) in {"online", "installing"}:
                continue

            updated = getattr(row, "updated_at", None)
            if updated is not None:
                try:
                    if getattr(updated, "tzinfo", None) is not None:
                        updated = updated.replace(tzinfo=None)
                    age = max(0.0, (now - updated).total_seconds())
                    if age < INSTALL_RETRY_SECONDS:
                        continue
                except Exception:
                    pass

            return name

        return None
    finally:
        db.close()


async def _install_candidate(
    tunnel_id: int,
    name: str,
) -> None:
    db = SessionLocal()
    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if (
            tunnel is None
            or not tunnel.is_active
            or _name(tunnel.mode) != "auto"
        ):
            return

        print(
            "[SmartAutoV21] INSTALL_START "
            f"tunnel={int(tunnel_id)} transport={name}",
            flush=True,
        )

        await install_transport(name, int(tunnel_id), db)

        print(
            "[SmartAutoV21] INSTALL_OK "
            f"tunnel={int(tunnel_id)} transport={name}",
            flush=True,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        db.rollback()
        print(
            "[SmartAutoV21] INSTALL_FAILED "
            f"tunnel={int(tunnel_id)} transport={name} "
            f"error={repr(exc)[:1000]}",
            flush=True,
        )
    finally:
        db.close()


def _maybe_schedule_install(tunnel_id: int) -> None:
    global _install_task

    if _install_task is not None and not _install_task.done():
        return

    loop = asyncio.get_running_loop()
    tid = int(tunnel_id)
    now = loop.time()
    last = _last_install_started.get(tid, float("-inf"))

    # Avoid a manager pass immediately scheduling another heavy install before
    # systemd/apt locks and node load settle.
    if now - float(last) < 20.0:
        return

    name = _install_candidate_name(tid)
    if not name:
        return

    _last_install_started[tid] = now
    _install_task = asyncio.create_task(
        _install_candidate(tid, name),
        name=f"twinpanel-smart-install-{tid}-{name}",
    )


async def candidate_health_remote_v21(
    tunnel_id: int,
    name: str,
    cfg: dict,
) -> tuple[str, dict]:
    global _BASE_OVERLAY_HEALTH

    name = _name(name)

    if name not in CANDIDATE_NAMES:
        if _BASE_OVERLAY_HEALTH is None:
            return name, {
                "ok": False,
                "latency_ms": None,
                "error": "smart_auto_base_probe_missing",
            }
        return await _BASE_OVERLAY_HEALTH(
            int(tunnel_id),
            name,
            cfg,
        )

    key = (int(tunnel_id), name)
    loop = asyncio.get_running_loop()
    cached = _candidate_health_cache.get(key)
    if cached is not None:
        stamp, result = cached
        if loop.time() - float(stamp) < HEALTH_CACHE_SECONDS:
            return name, dict(result)

    db = SessionLocal()
    ci = ce = None

    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is None:
            raise RuntimeError("tunnel_missing")

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if iran is None or exit_node is None:
            raise RuntimeError("node_missing")

        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(tunnel_id),
                TunnelTransport.transport == name,
            )
            .first()
        )
        if row is None or not row.enabled:
            raise RuntimeError("candidate_not_enabled")

        rt = _candidate_rt(name, int(tunnel_id))
        ci, ce = await connect_pair(iran, exit_node, db)

        async def local_state(conn, service: str, iface: str):
            result = await conn.run(
                "set +e\n"
                f"systemctl is-active {shlex.quote(service)} 2>/dev/null || true\n"
                f"systemctl show {shlex.quote(service)} -p NRestarts --value 2>/dev/null || echo 0\n"
                f"ip link show {shlex.quote(iface)} >/dev/null 2>&1; echo IFACE_RC=$?\n",
                check=False,
                timeout=20,
            )
            lines = (result.stdout or "").strip().splitlines()
            active = bool(lines and lines[0].strip() == "active")
            restarts = 0
            for line in lines[1:3]:
                try:
                    restarts = int(line.strip())
                    break
                except (TypeError, ValueError):
                    pass
            iface_ok = "IFACE_RC=0" in (result.stdout or "")
            return active, max(0, restarts), iface_ok

        iran_state, exit_state = await asyncio.gather(
            local_state(ci, rt["iran_service"], rt["interface"]),
            local_state(ce, rt["exit_service"], rt["interface"]),
        )

        if not iran_state[0] or not exit_state[0]:
            raise RuntimeError(
                "candidate_service_inactive:"
                f"iran={iran_state[0]} exit={exit_state[0]}"
            )
        if not iran_state[2] or not exit_state[2]:
            raise RuntimeError(
                "candidate_interface_missing:"
                f"iran={iran_state[2]} exit={exit_state[2]}"
            )

        health = await candidate_probe(
            ci,
            ce,
            name=name,
            tunnel_id=int(tunnel_id),
            rt=rt,
        )

        restart_count = int(iran_state[1]) + int(exit_state[1])
        now_epoch = time.time()
        state = _smart_state(row)
        prior_restarts = int(state.get("restart_count", restart_count) or 0)
        stable_since = _safe_float(state.get("stable_since_epoch"), None)

        if stable_since is None or restart_count != prior_restarts:
            stable_since = now_epoch

        stable_seconds = max(0.0, now_epoch - float(stable_since))
        loss = _safe_float(health.get("packet_loss_pct"), 0.0) or 0.0

        result = {
            "ok": bool(health.get("peer_ping"))
            and bool(health.get("tcp_egress"))
            and bool(health.get("udp_egress"))
            and loss <= MAX_PACKET_LOSS_PCT,
            "latency_ms": health.get("latency_ms"),
            "packet_loss_pct": loss,
            "restart_count": restart_count,
            "stable_seconds": stable_seconds,
            "egress_ip": health.get("egress_ip"),
            "error": None,
        }

        if not result["ok"]:
            result["error"] = "candidate_full_dataplane_probe_failed"

        _set_smart_state(
            row,
            merge={
                "version": 21,
                "last_probe_epoch": now_epoch,
                "last_probe_ok": bool(result["ok"]),
                "stable_since_epoch": stable_since,
                "stable_seconds": round(stable_seconds, 3),
                "restart_count": restart_count,
                "quarantine_reason": None if result["ok"] else "health_probe_failed",
                "quarantine_until_epoch": (
                    0.0 if result["ok"] else now_epoch + 120.0
                ),
            },
        )
        row.status = "online" if result["ok"] else "offline"
        row.latency_ms = result["latency_ms"] if result["ok"] else None
        row.last_error = result["error"]
        if result["ok"]:
            row.last_healthy_at = datetime.utcnow()
        db.commit()

        _candidate_health_cache[key] = (loop.time(), dict(result))
        return name, result

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        result = {
            "ok": False,
            "latency_ms": None,
            "packet_loss_pct": None,
            "restart_count": None,
            "stable_seconds": 0.0,
            "error": ("candidate_probe_exception:" + repr(exc))[:1400],
        }

        try:
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == name,
                )
                .first()
            )
            if row is not None:
                _set_smart_state(
                    row,
                    merge={
                        "version": 21,
                        "last_probe_epoch": time.time(),
                        "last_probe_ok": False,
                        "stable_since_epoch": time.time(),
                        "stable_seconds": 0.0,
                        "quarantine_reason": result["error"],
                        "quarantine_until_epoch": time.time() + 120.0,
                    },
                )
                row.status = "offline"
                row.latency_ms = None
                row.last_error = result["error"]
                db.commit()
        except Exception:
            db.rollback()

        _candidate_health_cache[key] = (loop.time(), dict(result))
        return name, result
    finally:
        await close_pair(ci, ce)
        db.close()


async def _run(conn, command: str, timeout: int = 12):
    return await conn.run(command, check=False, timeout=timeout)


async def _wait_ready(conn, logfile: str) -> bool:
    for _ in range(40):
        await asyncio.sleep(0.1)
        result = await _run(
            conn,
            "grep -q '^READY$' "
            + shlex.quote(logfile)
            + " 2>/dev/null; echo $?",
            4,
        )
        lines = (result.stdout or "").strip().splitlines()
        if lines and lines[-1] == "0":
            return True
    return False


def _port(tunnel_id: int, name: str, direction: int) -> int:
    seed = (
        int(tunnel_id) * 131
        + sum(ord(ch) for ch in str(name))
        + int(direction)
    )
    return 41000 + (seed % 18000)


async def _one_direction(
    sender,
    receiver,
    *,
    src: str,
    dst: str,
    port: int,
    label: str,
) -> float:
    logfile = f"/tmp/twinpanel-smart-v21-{port}-{label}.log"

    await _run(
        receiver,
        "rm -f " + shlex.quote(logfile) + " || true",
        4,
    )

    receiver_cmd = (
        "nohup timeout 15s python3 -u -c "
        + shlex.quote(RECEIVER_CODE)
        + " "
        + shlex.quote(dst)
        + " "
        + str(int(port))
        + " "
        + str(int(BENCHMARK_STREAMS))
        + " >"
        + shlex.quote(logfile)
        + " 2>&1 </dev/null &\ntrue"
    )
    await _run(receiver, receiver_cmd, 5)

    if not await _wait_ready(receiver, logfile):
        raise RuntimeError("throughput_receiver_not_ready:" + label)

    sender_cmd = (
        "timeout 12s python3 -u -c "
        + shlex.quote(SENDER_CODE)
        + " "
        + shlex.quote(src)
        + " "
        + shlex.quote(dst)
        + " "
        + str(int(port))
        + " "
        + str(float(BENCHMARK_SECONDS))
        + " "
        + str(int(BENCHMARK_MAX_BYTES))
        + " "
        + str(int(BENCHMARK_STREAMS))
    )

    tx = await _run(sender, sender_cmd, 14)
    if tx.exit_status != 0:
        raise RuntimeError(
            "throughput_sender_failed:"
            + label
            + ":"
            + ((tx.stderr or tx.stdout or "")[-600:])
        )

    await asyncio.sleep(0.5)

    rx = await _run(
        receiver,
        "cat "
        + shlex.quote(logfile)
        + " 2>/dev/null || true; rm -f "
        + shlex.quote(logfile)
        + " || true",
        5,
    )

    match = re.search(
        r"^RX_MBPS=([0-9]+(?:\.[0-9]+)?)$",
        rx.stdout or "",
        flags=re.MULTILINE,
    )
    if not match:
        raise RuntimeError("throughput_receiver_result_missing:" + label)

    value = float(match.group(1))
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError("throughput_receiver_result_invalid:" + label)

    return value


async def _benchmark_row(
    tunnel_id: int,
    row_id: int,
) -> None:
    db = SessionLocal()
    ci = ce = None

    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        row = db.get(TunnelTransport, int(row_id))

        if (
            tunnel is None
            or row is None
            or _name(tunnel.mode) != "auto"
            or not row.enabled
            or _status(row.status) != "online"
            or auto_block_reason(row)
        ):
            return

        meta = _benchmark_meta(row, int(tunnel_id))
        if meta is None:
            return

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if iran is None or exit_node is None:
            return

        ci, ce = await asyncio.gather(
            ssh_connect_saved(iran, db),
            ssh_connect_saved(exit_node, db),
        )

        name = _name(row.transport)

        # Exit -> Iran is user download direction. Iran -> Exit is upload.
        down = await _one_direction(
            ce,
            ci,
            src=meta["exit_ip"],
            dst=meta["iran_ip"],
            port=_port(tunnel_id, name, 1),
            label="download",
        )
        up = await _one_direction(
            ci,
            ce,
            src=meta["iran_ip"],
            dst=meta["exit_ip"],
            port=_port(tunnel_id, name, 2),
            label="upload",
        )

        weighted = (0.70 * float(down)) + (0.30 * float(up))
        now_epoch = time.time()

        db.expire_all()
        row = db.get(TunnelTransport, int(row_id))
        if row is None:
            return

        _set_smart_state(
            row,
            merge={
                "version": 21,
                "throughput": {
                    "measured_at_epoch": now_epoch,
                    "download_mbps": round(float(down), 3),
                    "upload_mbps": round(float(up), 3),
                    "weighted_mbps": round(float(weighted), 3),
                    "download_weight": 0.70,
                    "upload_weight": 0.30,
                    "streams": int(BENCHMARK_STREAMS),
                    "max_bytes_per_direction": int(BENCHMARK_MAX_BYTES),
                    "max_seconds_per_direction": float(BENCHMARK_SECONDS),
                    "source": "internal_tunnel_ip_tcp",
                },
            },
        )
        db.commit()

        print(
            "[SmartAutoV21] BENCHMARK "
            f"tunnel={int(tunnel_id)} transport={name} "
            f"down={down:.2f} up={up:.2f} "
            f"weighted={weighted:.2f}Mbps",
            flush=True,
        )

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(
            "[SmartAutoV21] BENCHMARK_FAILED "
            f"tunnel={int(tunnel_id)} row={int(row_id)} "
            f"error={repr(exc)[:1000]}",
            flush=True,
        )
    finally:
        await close_pair(ci, ce)
        db.close()


def _next_benchmark_row(
    tunnel_id: int,
    health: dict[str, dict],
) -> int | None:
    db = SessionLocal()
    try:
        rows = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(tunnel_id),
                TunnelTransport.enabled.is_(True),
            )
            .order_by(
                TunnelTransport.priority.asc(),
                TunnelTransport.id.asc(),
            )
            .all()
        )

        now = time.time()
        candidates: list[tuple[int, float, int]] = []

        for row in rows:
            name = _name(row.transport)
            result = health.get(name)
            if not _candidate_auto_eligible(row, result):
                continue
            if _benchmark_meta(row, int(tunnel_id)) is None:
                continue

            sample = _throughput_sample(row, now)
            if sample is None:
                # Unsampled candidates first.
                candidates.append((0, 0.0, int(row.id)))
                continue

            age = float(sample["age_seconds"])
            if age >= BENCHMARK_REFRESH_SECONDS:
                candidates.append((1, -age, int(row.id)))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return candidates[0][2]
    finally:
        db.close()


def _maybe_schedule_benchmark(
    tunnel_id: int,
    health: dict[str, dict],
) -> None:
    global _benchmark_task

    if _benchmark_task is not None and not _benchmark_task.done():
        return

    loop = asyncio.get_running_loop()
    tid = int(tunnel_id)
    now = loop.time()
    last = _last_benchmark_started.get(tid, float("-inf"))

    if now - float(last) < BENCHMARK_SCHEDULE_SECONDS:
        return

    row_id = _next_benchmark_row(tid, health)
    if row_id is None:
        return

    _last_benchmark_started[tid] = now
    _benchmark_task = asyncio.create_task(
        _benchmark_row(tid, int(row_id)),
        name=f"twinpanel-smart-benchmark-{tid}-{int(row_id)}",
    )


async def manage_2027_v21(
    tunnel_id: int,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    db = SessionLocal()

    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is None or not tunnel.is_active:
            return False, None

        # Manual mode is authoritative.
        if _name(tunnel.mode or "manual") != "auto":
            _reset_candidate(int(tunnel_id))
            return False, None

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if iran is None or exit_node is None:
            return False, None

        if not dry_run:
            _maybe_schedule_install(int(tunnel.id))

        rows = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(tunnel.id),
                TunnelTransport.enabled.is_(True),
            )
            .order_by(
                TunnelTransport.priority.asc(),
                TunnelTransport.id.asc(),
            )
            .all()
        )
        rows = [
            row
            for row in rows
            if _name(row.transport) in ALL_AUTO_NAMES
        ]

        if not rows:
            return False, None

        modern_rows = [
            row
            for row in rows
            if _name(row.transport)
            in (BASE_MODERN_NAMES | CANDIDATE_NAMES)
            and not auto_block_reason(row)
        ]

        health: dict[str, dict] = {}

        if modern_rows:
            health.update(
                await v7.probe_overlays(
                    int(tunnel.id),
                    modern_rows,
                )
            )

        # Keep the proven V6 full-dataplane legacy probe as emergency fallback.
        legacy_health, _legacy_best = await v7.probe_legacy(
            tunnel,
            iran,
            exit_node,
            db,
            rows,
        )
        health.update(legacy_health)

        # Seed any recently healthy row not touched by the bounded legacy probe.
        for row in rows:
            name = _name(row.transport)
            if name in health:
                continue
            seeded = _health_seed(row)
            if seeded is not None:
                health[name] = seeded

        # Persist modern health.
        if not dry_run and modern_rows:
            v7.write_overlay_rows(modern_rows, health)

        if not dry_run:
            # Persist explicit auto-block reason without deleting rollback paths.
            for row in rows:
                reason = auto_block_reason(row)
                if reason and _name(row.transport) == "quic_2027":
                    _set_smart_state(
                        row,
                        merge={
                            "version": 21,
                            "auto_blocked": True,
                            "auto_block_reason": reason,
                        },
                    )
            db.commit()

            _maybe_schedule_benchmark(
                int(tunnel.id),
                health,
            )

        ranked = _ranked(rows, health)
        best = ranked[0][0] if ranked else None
        scores = dict(ranked)

        if dry_run:
            print(
                "[SmartAutoV21] DRYRUN "
                f"tunnel={int(tunnel.id)} "
                f"active={_name(tunnel.active_transport) or 'none'} "
                f"best={best or 'none'} "
                f"scores={scores}",
                flush=True,
            )
            return best is not None, best

        active = _name(tunnel.active_transport)
        row_by_name = {
            _name(row.transport): row
            for row in rows
        }
        active_row = row_by_name.get(active)
        active_health = health.get(active)
        active_ok = bool(
            active_row
            and _candidate_auto_eligible(active_row, active_health)
        )
        tid = int(tunnel.id)

        if best is None:
            _reset_candidate(tid)
            _failure_count[tid] = _failure_count.get(tid, 0) + 1
            if _failure_count[tid] >= ACTIVE_FAILURE_THRESHOLD:
                preferred = _name(tunnel.preferred_transport) or active or "backhaul"
                v7.set_offline(db, tunnel, preferred)
            return True, None

        best_row = row_by_name[best]
        best_health = health[best]

        if active == best:
            _failure_count[tid] = 0
            _reset_candidate(tid)
            v7.keep_online(
                db,
                tunnel,
                active,
                best_health,
                best,
            )
            return True, active

        if not active_ok:
            _failure_count[tid] = _failure_count.get(tid, 0) + 1
            if _failure_count[tid] >= ACTIVE_FAILURE_THRESHOLD:
                v7.switch_to(
                    db,
                    tunnel,
                    best,
                    best_health,
                    best,
                    "smart_v21_active_unhealthy_or_quarantined",
                )
                return True, best

            v7.keep_online(
                db,
                tunnel,
                active,
                active_health,
                best,
            )
            return True, active

        _failure_count[tid] = 0

        # Healthy active transport is replaced only when the challenger has a
        # meaningful measured speed advantage. This is the anti-flap gate.
        if not _materially_faster(best_row, active_row):
            _reset_candidate(tid)
            v7.keep_online(
                db,
                tunnel,
                active,
                active_health,
                best,
            )
            return True, active

        if _dwell_seconds(tunnel) < MIN_DWELL_SECONDS:
            v7.keep_online(
                db,
                tunnel,
                active,
                active_health,
                best,
            )
            return True, active

        now = asyncio.get_running_loop().time()
        if _candidate_target.get(tid) != best:
            _candidate_target[tid] = best
            _candidate_since[tid] = now

        since = _candidate_since.get(tid)
        held = 0.0 if since is None else now - float(since)

        if held >= PROMOTION_HOLD_SECONDS:
            v7.switch_to(
                db,
                tunnel,
                best,
                best_health,
                best,
                "smart_v21_faster_stable_candidate",
            )
            return True, best

        v7.keep_online(
            db,
            tunnel,
            active,
            active_health,
            best,
        )
        return True, active

    finally:
        db.close()


def install_smart_transport_auto_v21() -> None:
    global _BASE_OVERLAY_HEALTH

    if _BASE_OVERLAY_HEALTH is None:
        _BASE_OVERLAY_HEALTH = v7.overlay_health_remote

    # V7 resolves these module globals at runtime.
    v7.OVERLAY_NAMES = set(v7.OVERLAY_NAMES) | set(CANDIDATE_NAMES)
    v7.SUPPORTED_NAMES = set(v7.SUPPORTED_NAMES) | set(CANDIDATE_NAMES)

    # V17/V18 remain useful for shared constants and existing public-direct
    # transport setup, but V21 becomes the authoritative selector.
    v17.MODERN_NAMES = frozenset(
        set(v17.MODERN_NAMES) | set(CANDIDATE_NAMES)
    )
    v17.MANAGED_TRANSPORT_NAMES = frozenset(
        set(v17.MANAGED_TRANSPORT_NAMES) | set(CANDIDATE_NAMES)
    )

    v7.overlay_health_remote = candidate_health_remote_v21
    v7.manage_2027 = manage_2027_v21
    v8._managed_tunnel_ids = managed_tunnel_ids_v21

    print(
        "TWINPANEL_SMART_TRANSPORT_AUTO_V21_ACTIVE "
        "candidates=kernel_gre,gost_tun,amneziawg,netrix "
        "download_weight=0.70 upload_weight=0.30 "
        f"stable={int(CANDIDATE_STABLE_SECONDS)}s "
        f"loss_limit={MAX_PACKET_LOSS_PCT:.1f}% "
        "quic_0.6.1_frag=auto_blocked",
        flush=True,
    )
