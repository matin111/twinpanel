from __future__ import annotations

import base64
import json
import math
import shlex
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..node_runtime_connection import connect_protocol_runtime
from ..singbox_outbound_import import IMPORTABLE_TYPES
from .singbox_outbounds import _node, _read_document, _valid_tag


PERFORMANCE_STATE_PATH = "/etc/twinpanel/sing-box/outbound-performance.json"
PERFORMANCE_SCHEMA = 1
MAX_HISTORY_PER_TAG = 20

router = APIRouter(
    prefix="/v1/settings/vpn/outbound-performance",
    tags=["outbound-performance-v261"],
    dependencies=[Depends(require_admin)],
)

BenchmarkProfile = Literal["quick", "standard", "full"]
ScoreProfile = Literal["balanced", "latency", "download", "upload", "stability"]


class OutboundBenchmarkIn(BaseModel):
    profile: BenchmarkProfile = "standard"
    score_profile: ScoreProfile = "balanced"


_SCORE_WEIGHTS: dict[str, dict[str, float]] = {
    "balanced": {
        "latency": 0.25,
        "jitter": 0.15,
        "success": 0.20,
        "download": 0.25,
        "upload": 0.15,
    },
    "latency": {
        "latency": 0.45,
        "jitter": 0.25,
        "success": 0.20,
        "download": 0.05,
        "upload": 0.05,
    },
    "download": {
        "latency": 0.15,
        "jitter": 0.10,
        "success": 0.15,
        "download": 0.50,
        "upload": 0.10,
    },
    "upload": {
        "latency": 0.15,
        "jitter": 0.10,
        "success": 0.15,
        "download": 0.10,
        "upload": 0.50,
    },
    "stability": {
        "latency": 0.20,
        "jitter": 0.25,
        "success": 0.35,
        "download": 0.10,
        "upload": 0.10,
    },
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _throughput_score(mbps: float | None, *, reference_mbps: float) -> float:
    if mbps is None or mbps <= 0:
        return 0.0
    return _clamp(100.0 * math.log1p(float(mbps)) / math.log1p(reference_mbps))


def score_benchmark(result: dict[str, Any], score_profile: str = "balanced") -> dict[str, Any]:
    """Return a transparent 0..100 route-quality score.

    The benchmark itself is authoritative. Scoring is only a ranking layer and
    never changes Production routing automatically. A failed end-to-end route is
    always score 0. HTTP probe loss is deliberately not called packet loss.
    """

    profile = score_profile if score_profile in _SCORE_WEIGHTS else "balanced"
    if not bool(result.get("ok")):
        return {"score": 0.0, "quality": "failed", "score_profile": profile}

    latency = result.get("latency_ms")
    jitter = result.get("jitter_ms")
    probe_loss = result.get("probe_loss_pct")
    download = result.get("download_mbps")
    upload = result.get("upload_mbps")

    latency_score = 0.0 if latency is None else _clamp(100.0 - max(float(latency) - 20.0, 0.0) * 0.45)
    jitter_score = 0.0 if jitter is None else _clamp(100.0 - float(jitter) * 4.0)
    success_score = 0.0 if probe_loss is None else _clamp(100.0 - float(probe_loss))
    download_score = _throughput_score(download, reference_mbps=500.0)
    upload_score = _throughput_score(upload, reference_mbps=200.0)

    components = {
        "latency": latency_score,
        "jitter": jitter_score,
        "success": success_score,
        "download": download_score,
        "upload": upload_score,
    }
    weights = _SCORE_WEIGHTS[profile]
    score = round(sum(components[key] * weights[key] for key in components), 1)
    quality = "excellent" if score >= 85 else "good" if score >= 70 else "fair" if score >= 50 else "poor"
    return {
        "score": score,
        "quality": quality,
        "score_profile": profile,
        "score_components": {key: round(value, 1) for key, value in components.items()},
    }


def _empty_state() -> dict[str, Any]:
    return {
        "schema": PERFORMANCE_SCHEMA,
        "updated_at": None,
        "latest": {},
        "history": {},
    }


def _clean_state(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _empty_state()
    latest = raw.get("latest") if isinstance(raw.get("latest"), dict) else {}
    history = raw.get("history") if isinstance(raw.get("history"), dict) else {}
    return {
        "schema": PERFORMANCE_SCHEMA,
        "updated_at": raw.get("updated_at"),
        "latest": {
            str(key): dict(value)
            for key, value in latest.items()
            if isinstance(value, dict)
        },
        "history": {
            str(key): [dict(item) for item in value[-MAX_HISTORY_PER_TAG:] if isinstance(item, dict)]
            for key, value in history.items()
            if isinstance(value, list)
        },
    }


async def _read_state(conn) -> dict[str, Any]:
    result = await conn.run(f"cat {shlex.quote(PERFORMANCE_STATE_PATH)}", check=False)
    if result.exit_status != 0 or not str(result.stdout or "").strip():
        return _empty_state()
    try:
        return _clean_state(json.loads(result.stdout))
    except Exception:
        return _empty_state()


async def _write_state(conn, state: dict[str, Any]) -> None:
    encoded = base64.b64encode(
        (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    ).decode("ascii")
    path = shlex.quote(PERFORMANCE_STATE_PATH)
    command = f'''set -eu
+STATE={path}
+mkdir -p "$(dirname "$STATE")"
+printf '%s' {shlex.quote(encoded)} | base64 -d > "${{STATE}}.new"
+chmod 600 "${{STATE}}.new"
+mv "${{STATE}}.new" "$STATE"
+'''.replace("\n+", "\n")
    result = await conn.run(command, check=False)
    if result.exit_status != 0:
        detail = str(result.stderr or result.stdout or "performance_state_write_failed").strip()
        raise HTTPException(
            status_code=502,
            detail={"message": "ذخیره تاریخچه تست Outbound ناموفق بود", "error": detail[-1200:]},
        )


async def _persist_result(conn, result: dict[str, Any]) -> dict[str, Any]:
    state = await _read_state(conn)
    tag = str(result.get("tag") or "").strip()
    if not tag:
        return state
    history = list((state.get("history") or {}).get(tag) or [])
    history.append(dict(result))
    history = history[-MAX_HISTORY_PER_TAG:]
    state.setdefault("history", {})[tag] = history
    state.setdefault("latest", {})[tag] = dict(result)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _write_state(conn, state)
    return state


def _benchmark_script(tag: str, profile: BenchmarkProfile) -> str:
    importable_types = sorted(IMPORTABLE_TYPES)
    return f'''from __future__ import annotations
import json
import os
import shutil
import socket
import statistics
import subprocess
import tempfile
import time
from datetime import datetime, timezone

CONFIG = "/etc/twinpanel/sing-box/config.json"
TAG = {tag!r}
PROFILE = {profile!r}
IMPORTABLE_TYPES = set({importable_types!r})
PROFILE_SETTINGS = {{
    "quick": {{"latency_samples": 4, "download_sizes": [1000000], "upload_sizes": [500000]}},
    "standard": {{"latency_samples": 6, "download_sizes": [1000000, 5000000, 10000000], "upload_sizes": [1000000, 5000000]}},
    "full": {{"latency_samples": 8, "download_sizes": [1000000, 5000000, 10000000, 25000000], "upload_sizes": [1000000, 5000000, 10000000]}},
}}
settings = PROFILE_SETTINGS[PROFILE]
result = {{
    "ok": False,
    "tag": TAG,
    "profile": PROFILE,
    "tested_at": datetime.now(timezone.utc).isoformat(),
    "tcp_ok": None,
    "tcp_ms": None,
    "e2e_ok": False,
    "exit_ip": None,
    "http_code": None,
    "latency_ms": None,
    "jitter_ms": None,
    "probe_loss_pct": None,
    "latency_samples_ms": [],
    "download_mbps": None,
    "upload_mbps": None,
    "download_samples": [],
    "upload_samples": [],
    "download_bytes": 0,
    "upload_bytes": 0,
    "throughput_ok": False,
    "error": None,
}}
process = None
config_path = None
log_path = None
upload_path = None
log_handle = None

def run_curl(curl, proxy, args, timeout):
    return subprocess.run(
        [curl, "-4", "-sS", "--socks5-hostname", proxy, "--connect-timeout", "8", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def parse_metrics(raw, expected):
    fields = (raw or "").strip().split("|")
    if len(fields) != expected:
        return None
    return fields


def stable_throughput(samples):
    values = [float(item["mbps"]) for item in samples if float(item.get("mbps") or 0) > 0]
    if not values:
        return None
    tail = values[-2:] if len(values) > 1 else values
    return round(statistics.median(tail), 2)

try:
    with open(CONFIG, "r", encoding="utf-8") as handle:
        doc = json.load(handle)
    outbounds = doc.get("outbounds") if isinstance(doc.get("outbounds"), list) else []
    target = next((item for item in outbounds if isinstance(item, dict) and str(item.get("tag") or "") == TAG), None)
    if target is None:
        raise RuntimeError("outbound_not_found")
    kind = str(target.get("type") or "").strip().lower()
    is_direct = TAG == "direct" and kind == "direct"
    is_imported = TAG.startswith("ext-") and kind in IMPORTABLE_TYPES
    if not is_direct and not is_imported:
        raise RuntimeError("outbound_not_benchmarkable")

    if is_imported:
        server = str(target.get("server") or "").strip()
        server_port = int(target.get("server_port") or 0)
        if not server or not 1 <= server_port <= 65535:
            raise RuntimeError("outbound_endpoint_missing")
        started = time.perf_counter()
        sock = socket.create_connection((server, server_port), timeout=6)
        sock.close()
        result["tcp_ok"] = True
        result["tcp_ms"] = round((time.perf_counter() - started) * 1000, 1)

    binary = "/usr/local/bin/twinpanel-sing-box"
    if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
        binary = shutil.which("sing-box") or ""
    if not binary:
        raise RuntimeError("singbox_binary_missing")
    curl = shutil.which("curl") or ""
    if not curl:
        raise RuntimeError("curl_missing")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    local_port = int(listener.getsockname()[1])
    listener.close()

    test_doc = {{
        "log": {{"level": "error", "timestamp": True}},
        "inbounds": [{{
            "type": "mixed",
            "tag": "twinpanel-outbound-performance",
            "listen": "127.0.0.1",
            "listen_port": local_port,
        }}],
        "outbounds": outbounds,
        "route": {{"final": TAG}},
    }}
    if isinstance(doc.get("dns"), dict):
        test_doc["dns"] = doc["dns"]
    if isinstance(doc.get("endpoints"), list):
        test_doc["endpoints"] = doc["endpoints"]

    fd, config_path = tempfile.mkstemp(prefix="twinpanel-outbound-performance-", suffix=".json")
    os.close(fd)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(test_doc, handle, ensure_ascii=False, indent=2)
        handle.write("\\n")
    os.chmod(config_path, 0o600)

    checked = subprocess.run([binary, "check", "-c", config_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12, check=False)
    if checked.returncode != 0:
        raise RuntimeError("test_config_invalid: " + (checked.stderr or checked.stdout)[-800:])

    log_fd, log_path = tempfile.mkstemp(prefix="twinpanel-outbound-performance-", suffix=".log")
    os.close(log_fd)
    log_handle = open(log_path, "w", encoding="utf-8")
    process = subprocess.Popen([binary, "run", "-c", config_path], stdout=log_handle, stderr=subprocess.STDOUT, text=True)
    ready = False
    for _ in range(40):
        if process.poll() is not None:
            break
        try:
            probe = socket.create_connection(("127.0.0.1", local_port), timeout=0.2)
            probe.close()
            ready = True
            break
        except OSError:
            time.sleep(0.1)
    if not ready:
        raise RuntimeError("test_core_not_ready")

    proxy = f"127.0.0.1:{{local_port}}"
    ip_run = run_curl(curl, proxy, ["--max-time", "20", "https://api.ipify.org"], 25)
    if ip_run.returncode != 0 or not (ip_run.stdout or "").strip():
        raise RuntimeError("egress_ip_failed: " + (ip_run.stderr or "")[-500:])
    result["exit_ip"] = (ip_run.stdout or "").strip()[:128]

    latency_values = []
    failed_probes = 0
    for index in range(int(settings["latency_samples"])):
        nonce = f"{{time.time_ns()}}-{{index}}"
        probe_run = run_curl(
            curl,
            proxy,
            ["-o", "/dev/null", "--max-time", "15", "-w", "%{{http_code}}|%{{time_starttransfer}}", f"https://speed.cloudflare.com/__down?bytes=0&nonce={{nonce}}"],
            20,
        )
        fields = parse_metrics(probe_run.stdout, 2) if probe_run.returncode == 0 else None
        if fields is None:
            failed_probes += 1
            continue
        try:
            code = int(fields[0])
            elapsed_ms = float(fields[1]) * 1000.0
        except Exception:
            failed_probes += 1
            continue
        if not 200 <= code < 500 or elapsed_ms <= 0:
            failed_probes += 1
            continue
        result["http_code"] = code
        latency_values.append(round(elapsed_ms, 2))

    probe_total = int(settings["latency_samples"])
    result["latency_samples_ms"] = latency_values
    result["probe_loss_pct"] = round((failed_probes / probe_total) * 100.0, 1) if probe_total else None
    if latency_values:
        result["latency_ms"] = round(statistics.median(latency_values), 1)
        if len(latency_values) > 1:
            diffs = [abs(latency_values[i] - latency_values[i - 1]) for i in range(1, len(latency_values))]
            result["jitter_ms"] = round(statistics.mean(diffs), 1)
        else:
            result["jitter_ms"] = 0.0
    result["e2e_ok"] = bool(latency_values)

    for size in settings["download_sizes"]:
        nonce = f"{{time.time_ns()}}-d-{{size}}"
        dl = run_curl(
            curl,
            proxy,
            ["-o", "/dev/null", "--max-time", "60", "-w", "%{{http_code}}|%{{speed_download}}|%{{size_download}}|%{{time_total}}", f"https://speed.cloudflare.com/__down?bytes={{size}}&nonce={{nonce}}"],
            70,
        )
        fields = parse_metrics(dl.stdout, 4) if dl.returncode == 0 else None
        if fields is None:
            continue
        try:
            code = int(fields[0])
            speed_bps = float(fields[1])
            transferred = int(float(fields[2]))
            elapsed = float(fields[3])
        except Exception:
            continue
        if not 200 <= code < 500 or speed_bps <= 0 or transferred <= 0:
            continue
        sample = {{"bytes": transferred, "seconds": round(elapsed, 3), "mbps": round(speed_bps * 8.0 / 1_000_000.0, 2)}}
        result["download_samples"].append(sample)
        result["download_bytes"] += transferred

    upload_fd, upload_path = tempfile.mkstemp(prefix="twinpanel-outbound-upload-", suffix=".bin")
    os.close(upload_fd)
    for size in settings["upload_sizes"]:
        os.truncate(upload_path, int(size))
        nonce = f"{{time.time_ns()}}-u-{{size}}"
        up = run_curl(
            curl,
            proxy,
            ["-o", "/dev/null", "--max-time", "60", "-X", "POST", "-H", "Content-Type: application/octet-stream", "--data-binary", f"@{{upload_path}}", "-w", "%{{http_code}}|%{{speed_upload}}|%{{size_upload}}|%{{time_total}}", f"https://speed.cloudflare.com/__up?nonce={{nonce}}"],
            70,
        )
        fields = parse_metrics(up.stdout, 4) if up.returncode == 0 else None
        if fields is None:
            continue
        try:
            code = int(fields[0])
            speed_bps = float(fields[1])
            transferred = int(float(fields[2]))
            elapsed = float(fields[3])
        except Exception:
            continue
        if not 200 <= code < 500 or speed_bps <= 0 or transferred <= 0:
            continue
        sample = {{"bytes": transferred, "seconds": round(elapsed, 3), "mbps": round(speed_bps * 8.0 / 1_000_000.0, 2)}}
        result["upload_samples"].append(sample)
        result["upload_bytes"] += transferred

    result["download_mbps"] = stable_throughput(result["download_samples"])
    result["upload_mbps"] = stable_throughput(result["upload_samples"])
    result["throughput_ok"] = bool(result["download_mbps"] and result["upload_mbps"])
    route_gate = bool(result["e2e_ok"] and result["exit_ip"])
    if is_imported:
        route_gate = bool(route_gate and result["tcp_ok"])
    result["ok"] = route_gate
except Exception as exc:
    result["error"] = str(exc)[:1200]
finally:
    if process is not None:
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
    if log_handle is not None:
        try:
            log_handle.close()
        except Exception:
            pass
    for path in (config_path, log_path, upload_path):
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass
print(json.dumps(result, ensure_ascii=False))
'''


def _benchmarkable_tags(doc: dict[str, Any]) -> list[str]:
    outbounds = doc.get("outbounds") if isinstance(doc.get("outbounds"), list) else []
    tags: list[str] = []
    for item in outbounds:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "").strip()
        kind = str(item.get("type") or "").strip().lower()
        if tag == "direct" and kind == "direct":
            tags.append(tag)
        elif tag.startswith("ext-") and kind in IMPORTABLE_TYPES:
            tags.append(tag)
    return tags


def _validate_target(doc: dict[str, Any], tag: str) -> None:
    if tag not in _benchmarkable_tags(doc):
        raise HTTPException(status_code=409, detail="این Outbound برای Benchmark ایزوله قابل استفاده نیست")


async def _run_benchmark(conn, *, tag: str, profile: BenchmarkProfile, score_profile: ScoreProfile) -> dict[str, Any]:
    script = _benchmark_script(tag, profile)
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    command = f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3"
    timeout = 120 if profile == "quick" else 240 if profile == "standard" else 420
    result = await conn.run(command, check=False, timeout=timeout)
    if result.exit_status != 0:
        detail = str(result.stderr or result.stdout or "outbound_benchmark_failed").strip()
        raise HTTPException(
            status_code=502,
            detail={"message": "Benchmark ایزوله Outbound اجرا نشد", "error": detail[-1800:]},
        )
    lines = [line.strip() for line in str(result.stdout or "").splitlines() if line.strip()]
    if not lines:
        raise HTTPException(status_code=502, detail="Benchmark Outbound نتیجه‌ای برنگرداند")
    try:
        data = json.loads(lines[-1])
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "پاسخ Benchmark معتبر نیست", "error": lines[-1][-1400:]},
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="پاسخ Benchmark معتبر نیست")
    data.update(score_benchmark(data, score_profile))
    return data


@router.get("/{node_id}")
async def outbound_performance_state(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        state = await _read_state(conn)
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        ranking = sorted(
            [dict(item) for item in latest.values() if isinstance(item, dict)],
            key=lambda item: (bool(item.get("ok")), float(item.get("score") or 0.0)),
            reverse=True,
        )
        return {
            "ok": True,
            "schema": PERFORMANCE_SCHEMA,
            "node_id": node.id,
            "node_name": node.name,
            "benchmarkable_tags": _benchmarkable_tags(doc),
            "profiles": ["quick", "standard", "full"],
            "score_profiles": list(_SCORE_WEIGHTS),
            "probe_loss_semantics": "application_probe_loss_not_packet_loss",
            "latest": latest,
            "history": state.get("history") or {},
            "ranking": ranking,
            "updated_at": state.get("updated_at"),
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/{tag}/test")
async def benchmark_outbound(
    node_id: int,
    tag: str,
    payload: OutboundBenchmarkIn,
    db: Session = Depends(get_db),
):
    node = _node(db, node_id)
    clean_tag = _valid_tag(tag)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        _validate_target(doc, clean_tag)
        data = await _run_benchmark(
            conn,
            tag=clean_tag,
            profile=payload.profile,
            score_profile=payload.score_profile,
        )
        await _persist_result(conn, data)
        return {"node_id": node.id, **data}
    finally:
        conn.close()
        await conn.wait_closed()


__all__ = [
    "MAX_HISTORY_PER_TAG",
    "PERFORMANCE_SCHEMA",
    "PERFORMANCE_STATE_PATH",
    "OutboundBenchmarkIn",
    "_benchmark_script",
    "_benchmarkable_tags",
    "_clean_state",
    "router",
    "score_benchmark",
]
