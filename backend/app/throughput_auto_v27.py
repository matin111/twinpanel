from __future__ import annotations

import asyncio
import json
import math
import re
import shlex
import time
from typing import Any

from . import transport_policy_v20 as v20
from . import tunnel_transport_manager_v7 as v7
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport
from .mtunnel_transport import mtunnel_runtime_values
from .routers.provision import ssh_connect_saved
from .ssh_tunnel import (
    ssh_tunnel_addresses,
    ssh_tunnel_backhaul_values,
    ssh_tunnel_interface,
    ssh_tunnel_services,
)
from .tp2027_transport import TP2027_TRANSPORTS


# ============================================================
# TWINPANEL THROUGHPUT-AWARE AUTO V27
#
# V20 intentionally uses latency/loss/stability only. Production testing showed
# that a path may be L3-healthy while carrying materially less throughput in one
# direction. V27 adds a bounded, cached qualification signal without turning the
# manager loop into a continuous speed-test engine.
#
# Design:
#   * Manual mode remains untouched.
#   * The normal V20 health loop still decides reachability and failover.
#   * A background job runs at most once per tunnel every 10 minutes.
#   * Each job benchmarks at most two routable L3 candidates (active/preferred
#     first, then one stale challenger when they are the same).
#   * Each direction is capped to 8 MiB and 1.5 seconds across four TCP flows.
#   * Results are persisted inside TunnelTransport.config_text and cached for
#     30 minutes, so a manager restart does not lose qualification data.
#   * Selection uses the WORST direction (floor Mbps), preventing a fast upload
#     from hiding a severely constrained download path.
#   * Unknown throughput receives only a small neutral penalty; it is never a
#     health failure and never removes Manual availability.
# ============================================================


MEASUREMENT_KEY = "throughput_auto_v27"
BENCHMARK_INTERVAL_SECONDS = 600.0
CACHE_TTL_SECONDS = 1800.0
BENCHMARK_SECONDS = 1.5
BENCHMARK_MAX_BYTES = 8 * 1024 * 1024
BENCHMARK_FLOWS = 4
UNKNOWN_THROUGHPUT_PENALTY = 12.0
MAX_THROUGHPUT_PENALTY = 80.0
GOOD_FLOOR_MBPS = 20.0

_BASE_MANAGE_2027 = None
_BASE_PERFORMANCE_SCORE = None

# (tunnel_id, transport) -> persisted measurement dict
_throughput_cache: dict[tuple[int, str], dict[str, Any]] = {}
_last_schedule: dict[int, float] = {}
_inflight: set[int] = set()
_cursor: dict[int, int] = {}


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _json_dict(raw: object) -> dict:
    if not raw:
        return {}

    try:
        value = json.loads(str(raw))
    except Exception:
        return {}

    return value if isinstance(value, dict) else {}


def _safe_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


def _cache_key(tunnel_id: int, name: str) -> tuple[int, str]:
    return int(tunnel_id), _name(name)


def _measurement_fresh(measurement: dict | None, now: float | None = None) -> bool:
    if not isinstance(measurement, dict):
        return False

    stamp = _safe_float(measurement.get("measured_at"))
    floor = _safe_float(measurement.get("floor_mbps"))

    if stamp is None or floor is None or floor < 0:
        return False

    current = float(time.time() if now is None else now)
    age = max(0.0, current - stamp)
    return age <= CACHE_TTL_SECONDS


def _measurement_from_row(row: TunnelTransport) -> dict | None:
    cfg = _json_dict(getattr(row, "config_text", None))
    value = cfg.get(MEASUREMENT_KEY)
    return dict(value) if isinstance(value, dict) else None


def hydrate_cache(tunnel_id: int, rows: list[TunnelTransport]) -> None:
    tid = int(tunnel_id)
    now = time.time()

    for row in rows:
        name = _name(getattr(row, "transport", ""))
        if not name:
            continue

        measurement = _measurement_from_row(row)
        key = _cache_key(tid, name)

        if _measurement_fresh(measurement, now):
            _throughput_cache[key] = dict(measurement or {})
        else:
            _throughput_cache.pop(key, None)


def throughput_penalty(measurement: dict | None) -> float:
    if not _measurement_fresh(measurement):
        return UNKNOWN_THROUGHPUT_PENALTY

    floor = max(
        0.25,
        float(measurement.get("floor_mbps") or 0.0),
    )

    # 20+ Mbps adds no penalty. 10 Mbps ~= +4, 5 Mbps ~= +12,
    # 1 Mbps ~= +76. This is strong enough to avoid a hard-capped path while
    # still leaving latency/loss/stability relevant among similarly fast paths.
    penalty = (80.0 / floor) - 4.0
    return max(0.0, min(MAX_THROUGHPUT_PENALTY, penalty))


def performance_score_v27(
    tunnel_id: int,
    name: str,
    result: dict | None,
) -> float:
    base_fn = _BASE_PERFORMANCE_SCORE or v20.performance_score
    base = float(base_fn(int(tunnel_id), _name(name), result))

    if not math.isfinite(base):
        return math.inf

    measurement = _throughput_cache.get(
        _cache_key(int(tunnel_id), name)
    )

    return base + throughput_penalty(measurement)


def _runtime_meta(
    tunnel: Tunnel,
    row: TunnelTransport,
) -> dict | None:
    name = _name(row.transport)

    if name in TP2027_TRANSPORTS:
        cfg = _json_dict(row.config_text)
        interface = str(cfg.get("interface") or "").strip()
        iran_ip = str(cfg.get("iran_ip") or "").split("/", 1)[0].strip()
        exit_ip = str(cfg.get("exit_ip") or "").split("/", 1)[0].strip()

        if interface and iran_ip and exit_ip:
            return {
                "interface": interface,
                "iran_ip": iran_ip,
                "exit_ip": exit_ip,
            }

        return None

    if name == "mtunnel":
        runtime = mtunnel_runtime_values(int(tunnel.id))
        return {
            "interface": str(runtime["interface"]),
            "iran_ip": str(runtime["iran_ip"]),
            "exit_ip": str(runtime["exit_ip"]),
        }

    if name == "backhaul":
        runtime = ssh_tunnel_backhaul_values(tunnel)
        return {
            "interface": str(runtime["interface"]),
            "iran_ip": str(runtime["iran_ip"]),
            "exit_ip": str(runtime["exit_ip"]),
        }

    if name == "ssh_tun":
        _network, iran_addr, exit_addr = ssh_tunnel_addresses(tunnel)
        return {
            "interface": ssh_tunnel_interface(tunnel),
            "iran_ip": iran_addr.split("/", 1)[0],
            "exit_ip": exit_addr.split("/", 1)[0],
        }

    # ssh_relay is not a routable L3 interface and is intentionally left with
    # the neutral unknown-throughput penalty rather than inventing a metric.
    return None


async def _endpoint_ready(conn, *, interface: str, local_ip: str, peer_ip: str) -> bool:
    command = f"""
set +e
ip link show dev {shlex.quote(interface)} >/dev/null 2>&1 || true
LINK_RC=$?
ip -4 addr show dev {shlex.quote(interface)} 2>/dev/null | grep -qw {shlex.quote(local_ip)}
ADDR_RC=$?
ping -I {shlex.quote(interface)} -c 2 -W 2 {shlex.quote(peer_ip)} >/dev/null 2>&1
PING_RC=$?
printf 'LINK_RC=%s\\nADDR_RC=%s\\nPING_RC=%s\\n' "$LINK_RC" "$ADDR_RC" "$PING_RC"
true
"""

    result = await conn.run(command, check=False, timeout=10)
    text = (result.stdout or "") + "\n" + (result.stderr or "")

    def marker(key: str) -> str:
        match = re.search(rf"^{re.escape(key)}=(.*)$", text, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""

    # ip link is intentionally not used as a hard gate here because the shell
    # command above is fail-open; address + peer reachability are authoritative.
    return marker("ADDR_RC") == "0" and marker("PING_RC") == "0"


_RX_SCRIPT = r'''
import socket
import sys
import threading
import time

ip = sys.argv[1]
port = int(sys.argv[2])
flows = int(sys.argv[3])

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind((ip, port))
srv.listen(flows + 2)
srv.settimeout(5)
print("READY", flush=True)

lock = threading.Lock()
state = {"bytes": 0, "first": None, "last": None}
threads = []


def worker(conn):
    conn.settimeout(2)
    while True:
        try:
            data = conn.recv(262144)
        except socket.timeout:
            continue
        except Exception:
            break
        if not data:
            break
        now = time.monotonic()
        with lock:
            state["bytes"] += len(data)
            if state["first"] is None:
                state["first"] = now
            state["last"] = now
    try:
        conn.close()
    except Exception:
        pass


end = time.monotonic() + 6
while len(threads) < flows and time.monotonic() < end:
    try:
        conn, _ = srv.accept()
    except socket.timeout:
        break
    except Exception:
        break
    t = threading.Thread(target=worker, args=(conn,), daemon=True)
    t.start()
    threads.append(t)

for t in threads:
    t.join(timeout=5)

first = state["first"]
last = state["last"]
elapsed = max((last - first) if first is not None and last is not None else 0.001, 0.001)
mbps = state["bytes"] * 8.0 / elapsed / 1_000_000.0
print(f"RX_BYTES={state['bytes']}", flush=True)
print(f"RX_SECONDS={elapsed:.4f}", flush=True)
print(f"RX_MBPS={mbps:.3f}", flush=True)
try:
    srv.close()
except Exception:
    pass
'''


_TX_SCRIPT = r'''
import socket
import sys
import threading
import time

src = sys.argv[1]
dst = sys.argv[2]
port = int(sys.argv[3])
flows = int(sys.argv[4])
seconds = float(sys.argv[5])
max_bytes = int(sys.argv[6])

lock = threading.Lock()
state = {"bytes": 0, "connected": 0}
per_flow = max(1, max_bytes // max(1, flows))
barrier = threading.Barrier(flows)


def worker():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    local = 0
    try:
        s.bind((src, 0))
        s.connect((dst, port))
        with lock:
            state["connected"] += 1
        try:
            barrier.wait(timeout=2)
        except Exception:
            pass
        payload = b"x" * 262144
        end = time.monotonic() + seconds
        while time.monotonic() < end and local < per_flow:
            chunk = payload[:min(len(payload), per_flow - local)]
            sent = s.send(chunk)
            if sent <= 0:
                break
            local += sent
    except Exception:
        pass
    finally:
        with lock:
            state["bytes"] += local
        try:
            s.shutdown(socket.SHUT_WR)
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass


threads = [threading.Thread(target=worker, daemon=True) for _ in range(flows)]
start = time.monotonic()
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=seconds + 4)
elapsed = max(time.monotonic() - start, 0.001)
print(f"TX_CONNECTED={state['connected']}")
print(f"TX_BYTES={state['bytes']}")
print(f"TX_SECONDS={elapsed:.4f}")
'''


async def _wait_ready(conn, logfile: str) -> bool:
    for _ in range(30):
        await asyncio.sleep(0.1)
        result = await conn.run(
            "grep -q '^READY$' " + shlex.quote(logfile) + " 2>/dev/null",
            check=False,
            timeout=3,
        )
        if result.exit_status == 0:
            return True
    return False


async def _direction_speed(
    sender,
    receiver,
    *,
    src: str,
    dst: str,
    port: int,
    logfile: str,
) -> float | None:
    await receiver.run("rm -f " + shlex.quote(logfile) + " || true", check=False, timeout=3)

    rx_cmd = (
        "timeout 12s python3 -u -c "
        + shlex.quote(_RX_SCRIPT)
        + " "
        + shlex.quote(dst)
        + " "
        + str(int(port))
        + " "
        + str(BENCHMARK_FLOWS)
        + " >"
        + shlex.quote(logfile)
        + " 2>&1 &"
    )

    await receiver.run(rx_cmd + "\ntrue", check=False, timeout=3)

    if not await _wait_ready(receiver, logfile):
        return None

    tx_cmd = (
        "timeout 8s python3 -u -c "
        + shlex.quote(_TX_SCRIPT)
        + " "
        + shlex.quote(src)
        + " "
        + shlex.quote(dst)
        + " "
        + str(int(port))
        + " "
        + str(BENCHMARK_FLOWS)
        + " "
        + str(BENCHMARK_SECONDS)
        + " "
        + str(BENCHMARK_MAX_BYTES)
    )

    await sender.run(tx_cmd, check=False, timeout=10)
    await asyncio.sleep(0.4)

    result = await receiver.run(
        "cat " + shlex.quote(logfile) + " 2>/dev/null || true; rm -f " + shlex.quote(logfile) + " || true",
        check=False,
        timeout=4,
    )

    match = re.search(r"^RX_MBPS=([0-9.]+)$", result.stdout or "", flags=re.MULTILINE)
    if not match:
        return None

    try:
        value = float(match.group(1))
    except (TypeError, ValueError):
        return None

    return value if math.isfinite(value) and value >= 0 else None


async def _benchmark_one(
    tunnel: Tunnel,
    row: TunnelTransport,
    iran: Node,
    exit_node: Node,
    db,
) -> dict | None:
    name = _name(row.transport)
    meta = _runtime_meta(tunnel, row)

    if meta is None:
        return None

    ci = ce = None

    try:
        ci, ce = await asyncio.gather(
            ssh_connect_saved(iran, db),
            ssh_connect_saved(exit_node, db),
        )

        interface = str(meta["interface"])
        iran_ip = str(meta["iran_ip"])
        exit_ip = str(meta["exit_ip"])

        iran_ready, exit_ready = await asyncio.gather(
            _endpoint_ready(ci, interface=interface, local_ip=iran_ip, peer_ip=exit_ip),
            _endpoint_ready(ce, interface=interface, local_ip=exit_ip, peer_ip=iran_ip),
        )

        if not iran_ready or not exit_ready:
            return None

        seed = sum(name.encode("utf-8")) + (int(tunnel.id) * 17)
        base_port = 46000 + (seed % 1500) * 2
        if base_port > 64000:
            base_port = 47000 + (int(tunnel.id) % 500)

        download = await _direction_speed(
            ce,
            ci,
            src=exit_ip,
            dst=iran_ip,
            port=base_port,
            logfile=f"/tmp/tp-v27-{int(tunnel.id)}-{name}-down.log",
        )

        upload = await _direction_speed(
            ci,
            ce,
            src=iran_ip,
            dst=exit_ip,
            port=base_port + 1,
            logfile=f"/tmp/tp-v27-{int(tunnel.id)}-{name}-up.log",
        )

        if download is None or upload is None:
            return None

        floor = min(download, upload)

        return {
            "measured_at": int(time.time()),
            "download_mbps": round(float(download), 3),
            "upload_mbps": round(float(upload), 3),
            "floor_mbps": round(float(floor), 3),
            "sample_seconds": BENCHMARK_SECONDS,
            "max_bytes_per_direction": BENCHMARK_MAX_BYTES,
            "flows": BENCHMARK_FLOWS,
            "source": "internal_overlay_tcp_v27",
        }

    except asyncio.CancelledError:
        raise
    except Exception:
        return None
    finally:
        for conn in (ci, ce):
            if conn is not None:
                try:
                    conn.close()
                    await conn.wait_closed()
                except Exception:
                    pass


async def _persist_measurement(tunnel_id: int, name: str, measurement: dict) -> None:
    db = SessionLocal()
    try:
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(tunnel_id),
                TunnelTransport.transport == _name(name),
            )
            .first()
        )

        if row is None:
            return

        cfg = _json_dict(row.config_text)
        cfg[MEASUREMENT_KEY] = dict(measurement)
        row.config_text = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
        db.commit()

        _throughput_cache[_cache_key(tunnel_id, name)] = dict(measurement)
    finally:
        db.close()


def _pick_targets(
    tunnel: Tunnel,
    rows: list[TunnelTransport],
) -> list[TunnelTransport]:
    eligible = [
        row
        for row in v20._enabled_rows(rows)
        if _status(getattr(row, "status", "")) == "online"
        and _runtime_meta(tunnel, row) is not None
    ]

    if not eligible:
        return []

    by_name = {_name(row.transport): row for row in eligible}
    ordered: list[TunnelTransport] = []

    for name in (
        _name(tunnel.active_transport),
        _name(tunnel.preferred_transport),
    ):
        row = by_name.get(name)
        if row is not None and row not in ordered:
            ordered.append(row)

    stale = [
        row
        for row in eligible
        if row not in ordered
        and not _measurement_fresh(
            _throughput_cache.get(_cache_key(int(tunnel.id), _name(row.transport)))
        )
    ]

    stale.sort(key=lambda row: (int(getattr(row, "priority", 10**9) or 10**9), int(getattr(row, "id", 0) or 0)))

    if stale and len(ordered) < 2:
        tid = int(tunnel.id)
        index = int(_cursor.get(tid, 0)) % len(stale)
        _cursor[tid] = int(_cursor.get(tid, 0)) + 1
        ordered.append(stale[index])

    return ordered[:2]


async def _benchmark_cycle(tunnel_id: int) -> None:
    tid = int(tunnel_id)
    db = SessionLocal()

    try:
        tunnel = db.get(Tunnel, tid)
        if tunnel is None or _name(tunnel.mode) != "auto" or not tunnel.is_active:
            return

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if iran is None or exit_node is None:
            return

        rows = v7.enabled_rows(db, tid)
        hydrate_cache(tid, rows)
        targets = _pick_targets(tunnel, rows)

        for row in targets:
            name = _name(row.transport)
            current = _throughput_cache.get(_cache_key(tid, name))

            # Fresh data for active/preferred is reused; the background pass is
            # qualification, not continuous load generation.
            if _measurement_fresh(current):
                continue

            measurement = await _benchmark_one(tunnel, row, iran, exit_node, db)
            if measurement is None:
                print(
                    f"[ThroughputAutoV27] tunnel={tid} transport={name} benchmark=skipped_or_failed",
                    flush=True,
                )
                continue

            await _persist_measurement(tid, name, measurement)

            print(
                f"[ThroughputAutoV27] tunnel={tid} transport={name} "
                f"download={measurement['download_mbps']:.2f}Mbps "
                f"upload={measurement['upload_mbps']:.2f}Mbps "
                f"floor={measurement['floor_mbps']:.2f}Mbps",
                flush=True,
            )

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(
            f"[ThroughputAutoV27] tunnel={tid} benchmark_exception={repr(exc)[:900]}",
            flush=True,
        )
    finally:
        db.close()
        _inflight.discard(tid)


async def manage_2027_v27(
    tunnel_id: int,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    tid = int(tunnel_id)

    # Hydrate persisted throughput before V20 calculates scores.
    db = SessionLocal()
    try:
        rows = v7.enabled_rows(db, tid)
        hydrate_cache(tid, rows)
    finally:
        db.close()

    base = _BASE_MANAGE_2027
    if base is None:
        return False, None

    handled, selected = await base(tid, dry_run=dry_run)

    if dry_run:
        return handled, selected

    now = time.time()
    last = float(_last_schedule.get(tid, 0.0))

    if tid not in _inflight and (now - last) >= BENCHMARK_INTERVAL_SECONDS:
        _last_schedule[tid] = now
        _inflight.add(tid)
        asyncio.create_task(_benchmark_cycle(tid))

    return handled, selected


def install_throughput_auto_v27() -> None:
    global _BASE_MANAGE_2027, _BASE_PERFORMANCE_SCORE

    if _BASE_PERFORMANCE_SCORE is None:
        _BASE_PERFORMANCE_SCORE = v20.performance_score

    if _BASE_MANAGE_2027 is None:
        _BASE_MANAGE_2027 = v7.manage_2027

    v20.performance_score = performance_score_v27
    v7.manage_2027 = manage_2027_v27

    print(
        "TWINPANEL_THROUGHPUT_AUTO_V27_ACTIVE "
        "metrics=latency,loss,stability,throughput "
        f"benchmark_interval={int(BENCHMARK_INTERVAL_SECONDS)}s "
        f"cache_ttl={int(CACHE_TTL_SECONDS)}s "
        f"sample={BENCHMARK_SECONDS:.1f}s "
        f"max_bytes={BENCHMARK_MAX_BYTES} "
        "directional_floor=1 background=1",
        flush=True,
    )
