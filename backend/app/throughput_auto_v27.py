from __future__ import annotations

import asyncio
import json
import math
import re
import shlex
import time
from types import SimpleNamespace

from . import transport_policy_v20 as v20
from . import tunnel_transport_manager_v7 as v7
from .auto_eligibility_v24 import auto_eligible
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport
from .routers.provision import ssh_connect_saved


# ============================================================
# TWINPANEL THROUGHPUT AUTO V27
#
# V20 intentionally scores latency/loss/stability only. Production testing on
# Tunnel #5 proved that a path can be L3-healthy while real directional
# throughput differs materially. V27 adds a bounded, cached throughput signal
# without turning the manager's fast health loop into a speedtest loop.
#
# Safety model:
#   * one background candidate benchmark globally at a time
#   * at most one candidate scheduled per tunnel every 5 minutes
#   * one candidate is re-qualified at most every 10 minutes
#   * each direction is capped at 4 MiB or 2 seconds
#   * benchmark is tunnel-IP to tunnel-IP only; no public speedtest service
#   * no route/firewall/service changes
#   * samples persist inside TunnelTransport.config_text
#   * throughput affects ranking only after at least two fresh samples exist
#   * Manual authority and V20 health/failover/hysteresis remain unchanged
# ============================================================


BENCHMARK_SCHEDULE_SECONDS = 300.0
BENCHMARK_MIN_REFRESH_SECONDS = 600.0
THROUGHPUT_SAMPLE_TTL_SECONDS = 1800.0
BENCHMARK_SECONDS = 2.0
BENCHMARK_MAX_BYTES = 4 * 1024 * 1024
THROUGHPUT_REFERENCE_MBPS = 20.0
THROUGHPUT_MAX_PENALTY = 40.0
UNKNOWN_THROUGHPUT_PENALTY = 20.0
MIN_FRESH_SAMPLES_FOR_SCORING = 2

_BASE_RANKED_ALL = None
_BASE_MANAGE_2027 = None

_benchmark_task: asyncio.Task | None = None
_last_benchmark_started: dict[int, float] = {}


RECEIVER_CODE = r'''
import socket,sys,time
ip=sys.argv[1]
port=int(sys.argv[2])
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind((ip,port))
s.listen(1)
s.settimeout(5)
print("READY",flush=True)
conn,_=s.accept()
conn.settimeout(1)
total=0
first=None
last=None
deadline=time.monotonic()+5
while time.monotonic()<deadline:
    try:
        data=conn.recv(262144)
    except socket.timeout:
        continue
    if not data:
        break
    now=time.monotonic()
    if first is None:
        first=now
    last=now
    total+=len(data)
try:
    conn.close()
except Exception:
    pass
try:
    s.close()
except Exception:
    pass
elapsed=max((last-first) if first is not None and last is not None else 0.001,0.001)
print(f"RX_BYTES={total}",flush=True)
print(f"RX_SECONDS={elapsed:.6f}",flush=True)
print(f"RX_MBPS={total*8.0/elapsed/1000000.0:.3f}",flush=True)
'''


SENDER_CODE = r'''
import socket,sys,time
src=sys.argv[1]
dst=sys.argv[2]
port=int(sys.argv[3])
seconds=float(sys.argv[4])
max_bytes=int(sys.argv[5])
s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
s.settimeout(2)
s.bind((src,0))
s.connect((dst,port))
payload=b"x"*262144
start=time.monotonic()
deadline=start+seconds
total=0
while time.monotonic()<deadline and total<max_bytes:
    chunk=payload[:min(len(payload),max_bytes-total)]
    try:
        sent=s.send(chunk)
    except socket.timeout:
        continue
    if sent<=0:
        break
    total+=sent
try:
    s.shutdown(socket.SHUT_WR)
except Exception:
    pass
try:
    s.close()
except Exception:
    pass
elapsed=max(time.monotonic()-start,0.001)
print(f"TX_BYTES={total}")
print(f"TX_SECONDS={elapsed:.6f}")
print(f"TX_MBPS={total*8.0/elapsed/1000000.0:.3f}")
'''


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _config(row) -> dict:
    raw = getattr(row, "config_text", None)
    if not raw:
        return {}
    try:
        data = json.loads(str(raw))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _benchmark_meta(row, tunnel_id: int) -> dict | None:
    cfg = _config(row)
    name = _name(getattr(row, "transport", ""))

    interface = str(cfg.get("interface") or "").strip()
    iran_ip = str(cfg.get("iran_ip") or "").strip().split("/", 1)[0]
    exit_ip = str(cfg.get("exit_ip") or "").strip().split("/", 1)[0]

    # MTunnel has deterministic runtime metadata even on older rows that do not
    # persist interface/IP fields in config_text.
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


def _sample(row, now_epoch: float | None = None) -> dict | None:
    cfg = _config(row)
    data = cfg.get("auto_throughput")

    if not isinstance(data, dict):
        return None

    try:
        measured = float(data.get("measured_at_epoch"))
        down = float(data.get("download_mbps"))
        up = float(data.get("upload_mbps"))
        effective = float(data.get("effective_mbps"))
    except (TypeError, ValueError):
        return None

    values = (measured, down, up, effective)
    if not all(math.isfinite(value) for value in values):
        return None
    if measured <= 0 or down <= 0 or up <= 0 or effective <= 0:
        return None

    now = time.time() if now_epoch is None else float(now_epoch)
    age = max(0.0, now - measured)

    if age > THROUGHPUT_SAMPLE_TTL_SECONDS:
        return None

    return {
        "measured_at_epoch": measured,
        "download_mbps": down,
        "upload_mbps": up,
        "effective_mbps": effective,
        "age_seconds": age,
    }


def throughput_penalty(effective_mbps: float) -> float:
    value = max(0.01, float(effective_mbps))
    normalized = min(value, THROUGHPUT_REFERENCE_MBPS) / THROUGHPUT_REFERENCE_MBPS
    return THROUGHPUT_MAX_PENALTY * (1.0 - normalized)


def _adjust_ranked_for_throughput(
    ranked: list[tuple[str, float]],
    rows: list,
    *,
    now_epoch: float | None = None,
) -> list[tuple[str, float]]:
    if not ranked:
        return []

    now = time.time() if now_epoch is None else float(now_epoch)
    row_by_name = {
        _name(getattr(row, "transport", "")): row
        for row in rows
    }

    samples = {
        name: _sample(row_by_name[name], now)
        for name, _score in ranked
        if name in row_by_name
    }

    fresh_count = sum(1 for item in samples.values() if item is not None)

    # Do not let one isolated measurement distort the whole candidate set.
    if fresh_count < MIN_FRESH_SAMPLES_FOR_SCORING:
        return list(ranked)

    adjusted: list[tuple[str, float, int]] = []

    for index, (name, base_score) in enumerate(ranked):
        sample = samples.get(name)
        if sample is None:
            penalty = UNKNOWN_THROUGHPUT_PENALTY
        else:
            penalty = throughput_penalty(sample["effective_mbps"])

        adjusted.append((name, float(base_score) + float(penalty), index))

    adjusted.sort(key=lambda item: (item[1], item[2], item[0]))
    return [(name, score) for name, score, _index in adjusted]


def ranked_all_v27(
    tunnel_id: int,
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> list[tuple[str, float]]:
    base = _BASE_RANKED_ALL
    if base is None:
        return []

    ranked = base(int(tunnel_id), rows, health)
    return _adjust_ranked_for_throughput(ranked, rows)


async def _run(conn, command: str, timeout: int = 12):
    return await conn.run(command, check=False, timeout=timeout)


async def _wait_ready(conn, logfile: str) -> bool:
    for _ in range(30):
        await asyncio.sleep(0.1)
        result = await _run(
            conn,
            "grep -q '^READY$' " + shlex.quote(logfile) + " 2>/dev/null; echo $?",
            4,
        )
        lines = (result.stdout or "").strip().splitlines()
        if lines and lines[-1] == "0":
            return True
    return False


def _port(tunnel_id: int, name: str, direction: int) -> int:
    seed = int(tunnel_id) * 131 + sum(ord(ch) for ch in str(name)) + int(direction)
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
    logfile = f"/tmp/twinpanel-v27-{port}-{label}.log"

    await _run(receiver, "rm -f " + shlex.quote(logfile) + " || true", 4)

    receiver_cmd = (
        "nohup timeout 8s python3 -u -c "
        + shlex.quote(RECEIVER_CODE)
        + " "
        + shlex.quote(dst)
        + " "
        + str(int(port))
        + " >"
        + shlex.quote(logfile)
        + " 2>&1 </dev/null &\ntrue"
    )
    await _run(receiver, receiver_cmd, 5)

    if not await _wait_ready(receiver, logfile):
        raise RuntimeError("throughput_receiver_not_ready:" + label)

    sender_cmd = (
        "timeout 6s python3 -u -c "
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
    )

    tx = await _run(sender, sender_cmd, 8)
    if tx.exit_status != 0:
        raise RuntimeError("throughput_sender_failed:" + label)

    await asyncio.sleep(0.5)

    rx = await _run(
        receiver,
        "cat " + shlex.quote(logfile) + " 2>/dev/null || true; rm -f " + shlex.quote(logfile) + " || true",
        5,
    )

    match = re.search(r"^RX_MBPS=([0-9]+(?:\.[0-9]+)?)$", rx.stdout or "", flags=re.MULTILINE)
    if not match:
        raise RuntimeError("throughput_receiver_result_missing:" + label)

    value = float(match.group(1))
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError("throughput_receiver_result_invalid:" + label)

    return value


async def _benchmark_candidate(tunnel_id: int, row_id: int) -> None:
    db = SessionLocal()
    ci = ce = None

    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        row = db.get(TunnelTransport, int(row_id))

        if tunnel is None or row is None:
            return
        if _name(getattr(tunnel, "mode", "")) != "auto":
            return
        if not bool(getattr(row, "enabled", False)):
            return
        if _status(getattr(row, "status", "")) != "online":
            return
        if not auto_eligible(row):
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

        name = meta["transport"]
        down = await _one_direction(
            ce,
            ci,
            src=meta["exit_ip"],
            dst=meta["iran_ip"],
            port=_port(tunnel_id, name, 1),
            label="down",
        )
        up = await _one_direction(
            ci,
            ce,
            src=meta["iran_ip"],
            dst=meta["exit_ip"],
            port=_port(tunnel_id, name, 2),
            label="up",
        )

        effective = min(float(down), float(up))
        measured = time.time()

        db.expire_all()
        current = db.get(TunnelTransport, int(row_id))
        if current is None:
            return

        cfg = _config(current)
        cfg["auto_throughput"] = {
            "version": 27,
            "measured_at_epoch": measured,
            "download_mbps": round(float(down), 3),
            "upload_mbps": round(float(up), 3),
            "effective_mbps": round(float(effective), 3),
            "max_bytes_per_direction": int(BENCHMARK_MAX_BYTES),
            "max_seconds_per_direction": float(BENCHMARK_SECONDS),
            "source": "internal_tunnel_ip_tcp",
        }
        current.config_text = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
        db.commit()

        print(
            "[ThroughputAutoV27] SAMPLE "
            f"tunnel={int(tunnel_id)} transport={name} "
            f"down={down:.2f} up={up:.2f} effective={effective:.2f}Mbps",
            flush=True,
        )

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(
            "[ThroughputAutoV27] SAMPLE_ERROR "
            f"tunnel={int(tunnel_id)} row={int(row_id)} error={repr(exc)[:900]}",
            flush=True,
        )
    finally:
        for conn in (ci, ce):
            if conn is not None:
                try:
                    conn.close()
                    await conn.wait_closed()
                except Exception:
                    pass
        db.close()


def _candidate_to_benchmark(tunnel_id: int) -> int | None:
    db = SessionLocal()
    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is None or _name(getattr(tunnel, "mode", "")) != "auto":
            return None

        rows = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(tunnel_id),
                TunnelTransport.enabled.is_(True),
            )
            .order_by(TunnelTransport.priority.asc(), TunnelTransport.id.asc())
            .all()
        )

        now = time.time()
        candidates: list[tuple[float, int]] = []

        for row in rows:
            if _status(getattr(row, "status", "")) != "online":
                continue
            if not auto_eligible(row):
                continue
            if _benchmark_meta(row, int(tunnel_id)) is None:
                continue

            sample = _sample(row, now)
            if sample is None:
                age = math.inf
            else:
                age = float(sample["age_seconds"])

            if math.isfinite(age) and age < BENCHMARK_MIN_REFRESH_SECONDS:
                continue

            freshness_key = -age if math.isfinite(age) else -1e18
            candidates.append((freshness_key, int(row.id)))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1]))
        return candidates[0][1]

    finally:
        db.close()


def _maybe_schedule_benchmark(tunnel_id: int) -> None:
    global _benchmark_task

    if _benchmark_task is not None and not _benchmark_task.done():
        return

    loop = asyncio.get_running_loop()
    now = loop.time()
    tid = int(tunnel_id)
    last = _last_benchmark_started.get(tid, float("-inf"))

    if now - float(last) < BENCHMARK_SCHEDULE_SECONDS:
        return

    row_id = _candidate_to_benchmark(tid)
    if row_id is None:
        return

    _last_benchmark_started[tid] = now
    _benchmark_task = asyncio.create_task(
        _benchmark_candidate(tid, int(row_id)),
        name=f"twinpanel-throughput-v27-{tid}-{int(row_id)}",
    )

    print(
        "[ThroughputAutoV27] SCHEDULED "
        f"tunnel={tid} row={int(row_id)}",
        flush=True,
    )


async def manage_2027_v27(
    tunnel_id: int,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    base = _BASE_MANAGE_2027
    if base is None:
        return False, None

    result = await base(int(tunnel_id), dry_run=dry_run)

    if not dry_run:
        _maybe_schedule_benchmark(int(tunnel_id))

    return result


def install_throughput_auto_v27() -> None:
    global _BASE_RANKED_ALL, _BASE_MANAGE_2027

    if _BASE_RANKED_ALL is None:
        _BASE_RANKED_ALL = v20.ranked_all
    if _BASE_MANAGE_2027 is None:
        _BASE_MANAGE_2027 = v7.manage_2027

    v20.ranked_all = ranked_all_v27
    v7.manage_2027 = manage_2027_v27

    print(
        "TWINPANEL_THROUGHPUT_AUTO_V27_ACTIVE "
        f"schedule={int(BENCHMARK_SCHEDULE_SECONDS)}s "
        f"refresh={int(BENCHMARK_MIN_REFRESH_SECONDS)}s "
        f"ttl={int(THROUGHPUT_SAMPLE_TTL_SECONDS)}s "
        f"bytes={int(BENCHMARK_MAX_BYTES)} "
        f"seconds={BENCHMARK_SECONDS:.1f} "
        f"reference={THROUGHPUT_REFERENCE_MBPS:.1f}Mbps "
        f"weight={THROUGHPUT_MAX_PENALTY:.1f} "
        f"min_samples={MIN_FRESH_SAMPLES_FOR_SCORING}",
        flush=True,
    )
