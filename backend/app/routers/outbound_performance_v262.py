from __future__ import annotations

import base64
import json
import shlex
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..node_runtime_connection import connect_protocol_runtime
from ..singbox_outbound_import import IMPORTABLE_TYPES
from .outbound_performance_v261 import (
    OutboundBenchmarkIn,
    _benchmarkable_tags,
    _persist_result,
    _read_state,
    _run_benchmark,
    _validate_target,
    score_benchmark,
)
from .singbox_outbounds import _node, _read_document, _valid_tag


router = APIRouter(
    prefix="/v1/settings/vpn/outbound-performance",
    tags=["outbound-performance-v262"],
    dependencies=[Depends(require_admin)],
)

BenchmarkProfile = Literal["quick", "standard", "full"]
TuningProfile = Literal["bbr_fq"]


class TuningApplyIn(BaseModel):
    profile: TuningProfile = "bbr_fq"


_BUFFERBLOAT_WEIGHT = {
    "balanced": 0.15,
    "latency": 0.20,
    "download": 0.08,
    "upload": 0.08,
    "stability": 0.25,
}


def _bufferbloat_score(value: float | None) -> float | None:
    if value is None:
        return None
    delay = max(0.0, float(value))
    if delay <= 5:
        return 100.0
    if delay <= 15:
        return 92.0
    if delay <= 30:
        return 82.0
    if delay <= 60:
        return 68.0
    if delay <= 100:
        return 50.0
    if delay <= 200:
        return 30.0
    return 10.0


def score_benchmark_v262(result: dict[str, Any], score_profile: str = "balanced") -> dict[str, Any]:
    effective = dict(result)
    effective["download_mbps"] = max(
        float(effective.get("download_mbps") or 0.0),
        float(effective.get("parallel_download_mbps") or 0.0),
    ) or None
    effective["upload_mbps"] = max(
        float(effective.get("upload_mbps") or 0.0),
        float(effective.get("parallel_upload_mbps") or 0.0),
    ) or None
    base = score_benchmark(effective, score_profile)
    if not bool(effective.get("ok")):
        return {**base, "score_version": 2}
    bb_score = _bufferbloat_score(effective.get("bufferbloat_ms"))
    if bb_score is None:
        return {**base, "score_version": 2, "bufferbloat_score": None}
    profile = str(base.get("score_profile") or "balanced")
    weight = _BUFFERBLOAT_WEIGHT.get(profile, _BUFFERBLOAT_WEIGHT["balanced"])
    score = round(float(base.get("score") or 0.0) * (1.0 - weight) + bb_score * weight, 1)
    quality = "excellent" if score >= 85 else "good" if score >= 70 else "fair" if score >= 50 else "poor"
    return {**base, "score": score, "quality": quality, "score_version": 2, "bufferbloat_score": round(bb_score, 1)}


def _advanced_diagnostics_script(
    tag: str,
    profile: BenchmarkProfile,
    *,
    idle_latency_ms: float | None,
    baseline_download_mbps: float | None,
) -> str:
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
IDLE_LATENCY_MS = {idle_latency_ms!r}
BASELINE_DOWNLOAD_MBPS = {baseline_download_mbps!r}
IMPORTABLE_TYPES = set({importable_types!r})
PROFILE_SETTINGS = {{
    "quick": {{"parallel_streams": 1, "download_each": 1000000, "upload_each": 500000, "loaded_samples": 2, "load_seconds": 1.0, "load_cap": 5000000}},
    "standard": {{"parallel_streams": 2, "download_each": 5000000, "upload_each": 2000000, "loaded_samples": 5, "load_seconds": 2.5, "load_cap": 50000000}},
    "full": {{"parallel_streams": 4, "download_each": 10000000, "upload_each": 5000000, "loaded_samples": 8, "load_seconds": 3.0, "load_cap": 100000000}},
}}
settings = PROFILE_SETTINGS[PROFILE]
result = {{
    "advanced_ok": False,
    "advanced_tested_at": datetime.now(timezone.utc).isoformat(),
    "tls_ms": None, "ttfb_ms": None, "http_version": None,
    "parallel_streams": int(settings["parallel_streams"]),
    "parallel_download_mbps": None, "parallel_upload_mbps": None,
    "parallel_download_bytes": 0, "parallel_upload_bytes": 0,
    "loaded_latency_ms": None, "loaded_jitter_ms": None,
    "loaded_probe_loss_pct": None, "bufferbloat_ms": None,
    "loaded_latency_samples_ms": [], "advanced_error": None,
}}
process = None
config_path = None
log_path = None
upload_path = None
log_handle = None
load_process = None

def curl_base(curl, proxy):
    return [curl, "-4", "-sS", "--socks5-hostname", proxy, "--connect-timeout", "8"]

def run_curl(curl, proxy, args, timeout):
    return subprocess.run([*curl_base(curl, proxy), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)

def parse_fields(raw, count):
    fields = (raw or "").strip().split("|")
    return fields if len(fields) == count else None

def parallel_download(curl, proxy, streams, bytes_each):
    jobs = []
    start = time.perf_counter()
    for index in range(streams):
        nonce = f"{{time.time_ns()}}-pd-{{index}}"
        jobs.append(subprocess.Popen([*curl_base(curl, proxy), "-o", "/dev/null", "--max-time", "75", "-w", "%{{size_download}}", f"https://speed.cloudflare.com/__down?bytes={{bytes_each}}&nonce={{nonce}}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    total = 0
    for job in jobs:
        stdout, _ = job.communicate(timeout=85)
        if job.returncode == 0:
            try: total += int(float((stdout or "0").strip()))
            except Exception: pass
    elapsed = max(time.perf_counter() - start, 0.001)
    return total, round(total * 8.0 / elapsed / 1_000_000.0, 2) if total > 0 else None

def parallel_upload(curl, proxy, streams, bytes_each, path):
    os.truncate(path, int(bytes_each))
    jobs = []
    start = time.perf_counter()
    for index in range(streams):
        nonce = f"{{time.time_ns()}}-pu-{{index}}"
        jobs.append(subprocess.Popen([*curl_base(curl, proxy), "-o", "/dev/null", "--max-time", "75", "-X", "POST", "-H", "Content-Type: application/octet-stream", "--data-binary", f"@{{path}}", "-w", "%{{size_upload}}", f"https://speed.cloudflare.com/__up?nonce={{nonce}}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    total = 0
    for job in jobs:
        stdout, _ = job.communicate(timeout=85)
        if job.returncode == 0:
            try: total += int(float((stdout or "0").strip()))
            except Exception: pass
    elapsed = max(time.perf_counter() - start, 0.001)
    return total, round(total * 8.0 / elapsed / 1_000_000.0, 2) if total > 0 else None

try:
    with open(CONFIG, "r", encoding="utf-8") as handle:
        doc = json.load(handle)
    outbounds = doc.get("outbounds") if isinstance(doc.get("outbounds"), list) else []
    target = next((item for item in outbounds if isinstance(item, dict) and str(item.get("tag") or "") == TAG), None)
    if target is None:
        raise RuntimeError("outbound_not_found")
    kind = str(target.get("type") or "").strip().lower()
    if not ((TAG == "direct" and kind == "direct") or (TAG.startswith("ext-") and kind in IMPORTABLE_TYPES)):
        raise RuntimeError("outbound_not_benchmarkable")

    binary = "/usr/local/bin/twinpanel-sing-box"
    if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
        binary = shutil.which("sing-box") or ""
    curl = shutil.which("curl") or ""
    if not binary: raise RuntimeError("singbox_binary_missing")
    if not curl: raise RuntimeError("curl_missing")

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    local_port = int(listener.getsockname()[1])
    listener.close()
    test_doc = {{
        "log": {{"level": "error", "timestamp": True}},
        "inbounds": [{{"type": "mixed", "tag": "twinpanel-outbound-performance-v262", "listen": "127.0.0.1", "listen_port": local_port}}],
        "outbounds": outbounds,
        "route": {{"final": TAG}},
    }}
    if isinstance(doc.get("dns"), dict): test_doc["dns"] = doc["dns"]
    if isinstance(doc.get("endpoints"), list): test_doc["endpoints"] = doc["endpoints"]

    fd, config_path = tempfile.mkstemp(prefix="twinpanel-outbound-performance-v262-", suffix=".json")
    os.close(fd)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(test_doc, handle, ensure_ascii=False, indent=2); handle.write("\\n")
    os.chmod(config_path, 0o600)
    checked = subprocess.run([binary, "check", "-c", config_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12, check=False)
    if checked.returncode != 0: raise RuntimeError("test_config_invalid: " + (checked.stderr or checked.stdout)[-800:])

    log_fd, log_path = tempfile.mkstemp(prefix="twinpanel-outbound-performance-v262-", suffix=".log")
    os.close(log_fd)
    log_handle = open(log_path, "w", encoding="utf-8")
    process = subprocess.Popen([binary, "run", "-c", config_path], stdout=log_handle, stderr=subprocess.STDOUT, text=True)
    ready = False
    for _ in range(40):
        if process.poll() is not None: break
        try:
            probe = socket.create_connection(("127.0.0.1", local_port), timeout=0.2); probe.close(); ready = True; break
        except OSError: time.sleep(0.1)
    if not ready: raise RuntimeError("test_core_not_ready")

    proxy = f"127.0.0.1:{{local_port}}"
    timing = run_curl(curl, proxy, ["-o", "/dev/null", "--max-time", "20", "-w", "%{{http_code}}|%{{http_version}}|%{{time_appconnect}}|%{{time_starttransfer}}", f"https://speed.cloudflare.com/__down?bytes=0&nonce={{time.time_ns()}}"], 25)
    fields = parse_fields(timing.stdout, 4) if timing.returncode == 0 else None
    if fields is not None:
        try:
            code = int(fields[0])
            if 200 <= code < 500:
                result["http_version"] = fields[1] or None
                result["tls_ms"] = round(float(fields[2]) * 1000.0, 1)
                result["ttfb_ms"] = round(float(fields[3]) * 1000.0, 1)
        except Exception: pass

    upload_fd, upload_path = tempfile.mkstemp(prefix="twinpanel-outbound-parallel-upload-", suffix=".bin"); os.close(upload_fd)
    streams = int(settings["parallel_streams"])
    dl_bytes, dl_mbps = parallel_download(curl, proxy, streams, int(settings["download_each"]))
    up_bytes, up_mbps = parallel_upload(curl, proxy, streams, int(settings["upload_each"]), upload_path)
    result["parallel_download_bytes"] = dl_bytes; result["parallel_download_mbps"] = dl_mbps
    result["parallel_upload_bytes"] = up_bytes; result["parallel_upload_mbps"] = up_mbps

    baseline = max(float(BASELINE_DOWNLOAD_MBPS or 0.0), 1.0)
    desired = int(baseline * 1_000_000.0 / 8.0 * float(settings["load_seconds"]))
    load_bytes = max(2_000_000, min(int(settings["load_cap"]), desired))
    load_process = subprocess.Popen([*curl_base(curl, proxy), "-o", "/dev/null", "--max-time", "90", f"https://speed.cloudflare.com/__down?bytes={{load_bytes}}&nonce={{time.time_ns()}}-load"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    loaded_values = []; failed = 0
    for index in range(int(settings["loaded_samples"])):
        probe = run_curl(curl, proxy, ["-o", "/dev/null", "--max-time", "15", "-w", "%{{http_code}}|%{{time_starttransfer}}", f"https://speed.cloudflare.com/__down?bytes=0&nonce={{time.time_ns()}}-lp-{{index}}"], 20)
        fields = parse_fields(probe.stdout, 2) if probe.returncode == 0 else None
        if fields is None: failed += 1
        else:
            try:
                code = int(fields[0]); value = float(fields[1]) * 1000.0
                if 200 <= code < 500 and value > 0: loaded_values.append(round(value, 2))
                else: failed += 1
            except Exception: failed += 1
        if load_process.poll() is not None and index >= 1: break
        time.sleep(0.12)
    if load_process.poll() is None:
        load_process.terminate()
        try: load_process.wait(timeout=2)
        except Exception: load_process.kill()
    load_process = None

    total_loaded = len(loaded_values) + failed
    result["loaded_latency_samples_ms"] = loaded_values
    result["loaded_probe_loss_pct"] = round((failed / total_loaded) * 100.0, 1) if total_loaded else None
    if loaded_values:
        loaded_median = statistics.median(loaded_values)
        result["loaded_latency_ms"] = round(loaded_median, 1)
        if len(loaded_values) > 1:
            diffs = [abs(loaded_values[i] - loaded_values[i - 1]) for i in range(1, len(loaded_values))]
            result["loaded_jitter_ms"] = round(statistics.mean(diffs), 1)
        else: result["loaded_jitter_ms"] = 0.0
        if IDLE_LATENCY_MS is not None:
            result["bufferbloat_ms"] = round(max(0.0, loaded_median - float(IDLE_LATENCY_MS)), 1)
    result["advanced_ok"] = bool(result["parallel_download_mbps"] or result["parallel_upload_mbps"] or result["loaded_latency_ms"] or result["tls_ms"])
except Exception as exc:
    result["advanced_error"] = str(exc)[:1200]
finally:
    if load_process is not None:
        try: load_process.terminate(); load_process.wait(timeout=2)
        except Exception:
            try: load_process.kill()
            except Exception: pass
    if process is not None:
        try: process.terminate(); process.wait(timeout=3)
        except Exception:
            try: process.kill()
            except Exception: pass
    if log_handle is not None:
        try: log_handle.close()
        except Exception: pass
    for path in (config_path, log_path, upload_path):
        if path:
            try: os.unlink(path)
            except Exception: pass
print(json.dumps(result, ensure_ascii=False))
'''


async def _run_advanced_diagnostics(conn, *, tag: str, profile: BenchmarkProfile, idle_latency_ms: float | None, baseline_download_mbps: float | None) -> dict[str, Any]:
    script = _advanced_diagnostics_script(tag, profile, idle_latency_ms=idle_latency_ms, baseline_download_mbps=baseline_download_mbps)
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    result = await conn.run(f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3", check=False, timeout=120 if profile == "quick" else 300 if profile == "standard" else 540)
    if result.exit_status != 0:
        return {"advanced_ok": False, "advanced_error": str(result.stderr or result.stdout or "advanced_benchmark_failed")[-1800:]}
    lines = [line.strip() for line in str(result.stdout or "").splitlines() if line.strip()]
    if not lines:
        return {"advanced_ok": False, "advanced_error": "advanced_benchmark_no_result"}
    try: data = json.loads(lines[-1])
    except Exception: return {"advanced_ok": False, "advanced_error": lines[-1][-1400:]}
    return data if isinstance(data, dict) else {"advanced_ok": False, "advanced_error": "advanced_benchmark_invalid_result"}


def _tuning_audit_script() -> str:
    return r'''from __future__ import annotations
import json
import os
import shutil
import subprocess

def run(args):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()

def sysctl(name):
    rc, out, _ = run(["sysctl", "-n", name]); return out if rc == 0 else None

def loadable(module):
    if not shutil.which("modprobe"): return False
    rc, _, _ = run(["modprobe", "-n", "-q", module]); return rc == 0

rc, route, _ = run(["ip", "-4", "route", "show", "default"])
iface = None
if rc == 0:
    parts = route.split()
    if "dev" in parts:
        try: iface = parts[parts.index("dev") + 1]
        except Exception: iface = None
available_cc = (sysctl("net.ipv4.tcp_available_congestion_control") or "").split()
current_cc = sysctl("net.ipv4.tcp_congestion_control")
default_qdisc = sysctl("net.core.default_qdisc")
qdisc = None
if iface and shutil.which("tc"):
    _, out, _ = run(["tc", "qdisc", "show", "dev", iface]); qdisc = out or None
offloads = None
if iface and shutil.which("ethtool"):
    _, out, _ = run(["ethtool", "-k", iface])
    if out:
        wanted = []
        for line in out.splitlines():
            key = line.strip().split(":", 1)[0]
            if key in {"tcp-segmentation-offload", "generic-segmentation-offload", "generic-receive-offload", "large-receive-offload"}: wanted.append(line.strip())
        offloads = wanted
bbr_loadable = loadable("tcp_bbr")
fq_current = default_qdisc == "fq" or bool(qdisc and (" fq " in f" {qdisc} " or "fq 0:" in qdisc))
recommendations = []
if "bbr" not in available_cc and not bbr_loadable: recommendations.append("bbr_unavailable_on_kernel")
elif current_cc != "bbr": recommendations.append("bbr_available_not_enabled")
if default_qdisc != "fq": recommendations.append("fq_default_not_enabled")
if sysctl("net.ipv4.tcp_mtu_probing") == "0": recommendations.append("tcp_mtu_probing_disabled_review_only")
print(json.dumps({
    "ok": True, "kernel": os.uname().release, "default_interface": iface,
    "tcp_congestion_control": current_cc, "tcp_available_congestion_control": available_cc,
    "default_qdisc": default_qdisc, "live_qdisc": qdisc,
    "tcp_mtu_probing": sysctl("net.ipv4.tcp_mtu_probing"),
    "rmem_max": sysctl("net.core.rmem_max"), "wmem_max": sysctl("net.core.wmem_max"),
    "tcp_rmem": sysctl("net.ipv4.tcp_rmem"), "tcp_wmem": sysctl("net.ipv4.tcp_wmem"),
    "bbr_supported": "bbr" in available_cc, "bbr_loadable": bbr_loadable,
    "fq_loadable": loadable("sch_fq") or fq_current,
    "accelerator_active": current_cc == "bbr" and default_qdisc == "fq",
    "live_qdisc_unchanged_by_profile": True, "offloads": offloads,
    "recommendations": recommendations,
}, ensure_ascii=False))
'''


def _tuning_apply_script() -> str:
    return r'''from __future__ import annotations
import base64
import json
import pathlib
import shutil
import subprocess

STATE = pathlib.Path("/etc/twinpanel/performance/tcp-accelerator-backup.json")
PROFILE = pathlib.Path("/etc/sysctl.d/91-twinpanel-outbound-performance.conf")
STATE.parent.mkdir(parents=True, exist_ok=True)

def run(args, check=False):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if check and proc.returncode != 0: raise RuntimeError((proc.stderr or proc.stdout or "command_failed")[-1200:])
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()

def sysctl(name):
    rc, out, _ = run(["sysctl", "-n", name]); return out if rc == 0 else None

if not STATE.exists():
    previous_profile = PROFILE.read_bytes() if PROFILE.exists() else None
    backup = {
        "tcp_congestion_control": sysctl("net.ipv4.tcp_congestion_control"),
        "default_qdisc": sysctl("net.core.default_qdisc"),
        "profile_existed": PROFILE.exists(),
        "profile_b64": base64.b64encode(previous_profile).decode("ascii") if previous_profile is not None else None,
    }
    tmp = STATE.with_suffix(".json.new"); tmp.write_text(json.dumps(backup, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); tmp.chmod(0o600); tmp.replace(STATE)
if shutil.which("modprobe"):
    run(["modprobe", "tcp_bbr"]); run(["modprobe", "sch_fq"])
available = (sysctl("net.ipv4.tcp_available_congestion_control") or "").split()
if "bbr" not in available: raise RuntimeError("bbr_unavailable_on_kernel")
profile_text = "# Managed by TwinPanel Outbound Performance Lab\nnet.ipv4.tcp_congestion_control=bbr\nnet.core.default_qdisc=fq\n"
tmp_profile = PROFILE.with_suffix(".conf.new"); tmp_profile.write_text(profile_text, encoding="utf-8"); tmp_profile.chmod(0o644); tmp_profile.replace(PROFILE)
run(["sysctl", "-w", "net.ipv4.tcp_congestion_control=bbr"], check=True)
run(["sysctl", "-w", "net.core.default_qdisc=fq"], check=True)
print(json.dumps({"ok": True, "tcp_congestion_control": sysctl("net.ipv4.tcp_congestion_control"), "default_qdisc": sysctl("net.core.default_qdisc"), "note": "Existing live qdisc is intentionally not replaced; routes/tunnels are not recycled."}, ensure_ascii=False))
'''


def _tuning_rollback_script() -> str:
    return r'''from __future__ import annotations
import base64
import json
import pathlib
import subprocess

STATE = pathlib.Path("/etc/twinpanel/performance/tcp-accelerator-backup.json")
PROFILE = pathlib.Path("/etc/sysctl.d/91-twinpanel-outbound-performance.conf")

def run(args, check=False):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if check and proc.returncode != 0: raise RuntimeError((proc.stderr or proc.stdout or "command_failed")[-1200:])
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()

def sysctl(name):
    rc, out, _ = run(["sysctl", "-n", name]); return out if rc == 0 else None

if not STATE.exists(): raise RuntimeError("tuning_backup_not_found")
backup = json.loads(STATE.read_text(encoding="utf-8"))
if backup.get("profile_existed"):
    raw = base64.b64decode(str(backup.get("profile_b64") or "")); tmp = PROFILE.with_suffix(".conf.rollback"); tmp.write_bytes(raw); tmp.chmod(0o644); tmp.replace(PROFILE)
else:
    try: PROFILE.unlink()
    except FileNotFoundError: pass
old_cc = str(backup.get("tcp_congestion_control") or "").strip(); old_qdisc = str(backup.get("default_qdisc") or "").strip()
if old_cc: run(["sysctl", "-w", f"net.ipv4.tcp_congestion_control={{old_cc}}"], check=True)
if old_qdisc: run(["sysctl", "-w", f"net.core.default_qdisc={{old_qdisc}}"], check=True)
STATE.unlink()
print(json.dumps({"ok": True, "tcp_congestion_control": sysctl("net.ipv4.tcp_congestion_control"), "default_qdisc": sysctl("net.core.default_qdisc"), "note": "TwinPanel profile rolled back; existing live qdisc was never replaced."}, ensure_ascii=False))
'''


async def _run_json_script(conn, script: str, *, timeout: int = 45) -> dict[str, Any]:
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    result = await conn.run(f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3", check=False, timeout=timeout)
    lines = [line.strip() for line in str(result.stdout or "").splitlines() if line.strip()]
    if result.exit_status != 0 or not lines:
        detail = str(result.stderr or result.stdout or "remote_performance_command_failed").strip()
        raise HTTPException(status_code=502, detail={"message": "عملیات Performance روی نود ناموفق بود", "error": detail[-1800:]})
    try: data = json.loads(lines[-1])
    except Exception as exc: raise HTTPException(status_code=502, detail={"message": "پاسخ Performance معتبر نیست", "error": lines[-1][-1400:]}) from exc
    if not isinstance(data, dict): raise HTTPException(status_code=502, detail="پاسخ Performance معتبر نیست")
    return data


@router.post("/{node_id}/{tag}/advanced-test")
async def advanced_benchmark_outbound(node_id: int, tag: str, payload: OutboundBenchmarkIn, db: Session = Depends(get_db)):
    node = _node(db, node_id); clean_tag = _valid_tag(tag); conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn); _validate_target(doc, clean_tag)
        baseline = await _run_benchmark(conn, tag=clean_tag, profile=payload.profile, score_profile=payload.score_profile)
        advanced = await _run_advanced_diagnostics(conn, tag=clean_tag, profile=payload.profile, idle_latency_ms=baseline.get("latency_ms"), baseline_download_mbps=baseline.get("download_mbps"))
        merged = {**baseline, **advanced}; merged.update(score_benchmark_v262(merged, payload.score_profile)); await _persist_result(conn, merged)
        return {"node_id": node.id, **merged}
    finally:
        conn.close(); await conn.wait_closed()


@router.get("/{node_id}/tuning")
async def outbound_tuning_audit(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id); conn = await connect_protocol_runtime(node, db)
    try: return {"node_id": node.id, "node_name": node.name, **(await _run_json_script(conn, _tuning_audit_script(), timeout=45))}
    finally: conn.close(); await conn.wait_closed()


@router.post("/{node_id}/tuning/apply")
async def outbound_tuning_apply(node_id: int, payload: TuningApplyIn, db: Session = Depends(get_db)):
    if payload.profile != "bbr_fq": raise HTTPException(status_code=409, detail="پروفایل Performance پشتیبانی نمی‌شود")
    node = _node(db, node_id); conn = await connect_protocol_runtime(node, db)
    try: return {"node_id": node.id, "node_name": node.name, "profile": payload.profile, **(await _run_json_script(conn, _tuning_apply_script(), timeout=60))}
    finally: conn.close(); await conn.wait_closed()


@router.post("/{node_id}/tuning/rollback")
async def outbound_tuning_rollback(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id); conn = await connect_protocol_runtime(node, db)
    try: return {"node_id": node.id, "node_name": node.name, **(await _run_json_script(conn, _tuning_rollback_script(), timeout=60))}
    finally: conn.close(); await conn.wait_closed()


@router.get("/{node_id}/advanced-state")
async def outbound_advanced_state(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id); conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn); state = await _read_state(conn)
        return {
            "ok": True, "node_id": node.id, "node_name": node.name,
            "benchmarkable_tags": _benchmarkable_tags(doc),
            "latest": state.get("latest") or {}, "history": state.get("history") or {},
            "advanced_metrics": ["parallel_download_mbps", "parallel_upload_mbps", "loaded_latency_ms", "loaded_jitter_ms", "loaded_probe_loss_pct", "bufferbloat_ms", "tls_ms", "ttfb_ms", "http_version"],
            "tuning_profiles": ["bbr_fq"],
            "safety": {"production_route_unchanged_during_test": True, "live_qdisc_not_replaced": True, "automatic_tuning_disabled": True},
        }
    finally: conn.close(); await conn.wait_closed()


__all__ = ["TuningApplyIn", "_advanced_diagnostics_script", "_bufferbloat_score", "_tuning_apply_script", "_tuning_audit_script", "_tuning_rollback_script", "router", "score_benchmark_v262"]
