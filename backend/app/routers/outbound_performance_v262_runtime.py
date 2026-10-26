from __future__ import annotations

import base64
import json
import shlex
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..node_runtime_connection import connect_protocol_runtime
from .outbound_performance_v261 import (
    OutboundBenchmarkIn,
    _benchmarkable_tags,
    _persist_result,
    _read_state,
    _run_benchmark,
    _validate_target,
)
from .outbound_performance_v262 import (
    TuningApplyIn,
    _run_advanced_diagnostics,
    _tuning_audit_script,
    score_benchmark_v262,
)
from .singbox_outbounds import _node, _read_document, _valid_tag


router = APIRouter(
    prefix="/v1/settings/vpn/outbound-performance",
    tags=["outbound-performance-v262"],
    dependencies=[Depends(require_admin)],
)


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
    if check and proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "command_failed")[-1200:])
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()

def sysctl(name):
    rc, out, _ = run(["sysctl", "-n", name])
    return out if rc == 0 else None

previous_profile = PROFILE.read_bytes() if PROFILE.exists() else None
backup = {
    "tcp_congestion_control": sysctl("net.ipv4.tcp_congestion_control"),
    "default_qdisc": sysctl("net.core.default_qdisc"),
    "profile_existed": PROFILE.exists(),
    "profile_b64": base64.b64encode(previous_profile).decode("ascii") if previous_profile is not None else None,
}
if shutil.which("modprobe"):
    run(["modprobe", "tcp_bbr"])
    run(["modprobe", "sch_fq"])
available = (sysctl("net.ipv4.tcp_available_congestion_control") or "").split()
if "bbr" not in available:
    raise RuntimeError("bbr_unavailable_on_kernel")
if not STATE.exists():
    tmp = STATE.with_suffix(".json.new")
    tmp.write_text(json.dumps(backup, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(STATE)

def restore_runtime():
    old_cc = str(backup.get("tcp_congestion_control") or "").strip()
    old_qdisc = str(backup.get("default_qdisc") or "").strip()
    if old_cc:
        run(["sysctl", "-w", f"net.ipv4.tcp_congestion_control={old_cc}"])
    if old_qdisc:
        run(["sysctl", "-w", f"net.core.default_qdisc={old_qdisc}"])
    if backup.get("profile_existed"):
        raw = base64.b64decode(str(backup.get("profile_b64") or ""))
        tmp = PROFILE.with_suffix(".conf.restore")
        tmp.write_bytes(raw)
        tmp.chmod(0o644)
        tmp.replace(PROFILE)
    else:
        try:
            PROFILE.unlink()
        except FileNotFoundError:
            pass

try:
    profile_text = "# Managed by TwinPanel Outbound Performance Lab\nnet.ipv4.tcp_congestion_control=bbr\nnet.core.default_qdisc=fq\n"
    tmp_profile = PROFILE.with_suffix(".conf.new")
    tmp_profile.write_text(profile_text, encoding="utf-8")
    tmp_profile.chmod(0o644)
    tmp_profile.replace(PROFILE)
    run(["sysctl", "-w", "net.ipv4.tcp_congestion_control=bbr"], check=True)
    run(["sysctl", "-w", "net.core.default_qdisc=fq"], check=True)
except Exception:
    restore_runtime()
    raise

print(json.dumps({
    "ok": True,
    "tcp_congestion_control": sysctl("net.ipv4.tcp_congestion_control"),
    "default_qdisc": sysctl("net.core.default_qdisc"),
    "note": "Existing live qdisc is intentionally not replaced; routes/tunnels are not recycled.",
}, ensure_ascii=False))
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
    if check and proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "command_failed")[-1200:])
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()

def sysctl(name):
    rc, out, _ = run(["sysctl", "-n", name])
    return out if rc == 0 else None

if not STATE.exists():
    raise RuntimeError("tuning_backup_not_found")
backup = json.loads(STATE.read_text(encoding="utf-8"))
if backup.get("profile_existed"):
    raw = base64.b64decode(str(backup.get("profile_b64") or ""))
    tmp = PROFILE.with_suffix(".conf.rollback")
    tmp.write_bytes(raw)
    tmp.chmod(0o644)
    tmp.replace(PROFILE)
else:
    try:
        PROFILE.unlink()
    except FileNotFoundError:
        pass
old_cc = str(backup.get("tcp_congestion_control") or "").strip()
old_qdisc = str(backup.get("default_qdisc") or "").strip()
if old_cc:
    run(["sysctl", "-w", f"net.ipv4.tcp_congestion_control={old_cc}"], check=True)
if old_qdisc:
    run(["sysctl", "-w", f"net.core.default_qdisc={old_qdisc}"], check=True)
STATE.unlink()
print(json.dumps({
    "ok": True,
    "tcp_congestion_control": sysctl("net.ipv4.tcp_congestion_control"),
    "default_qdisc": sysctl("net.core.default_qdisc"),
    "note": "TwinPanel profile rolled back; existing live qdisc was never replaced.",
}, ensure_ascii=False))
'''


async def _run_json_script(conn, script: str, *, timeout: int = 45) -> dict[str, Any]:
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    result = await conn.run(f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3", check=False, timeout=timeout)
    lines = [line.strip() for line in str(result.stdout or "").splitlines() if line.strip()]
    if result.exit_status != 0 or not lines:
        detail = str(result.stderr or result.stdout or "remote_performance_command_failed").strip()
        raise HTTPException(status_code=502, detail={"message": "عملیات Performance روی نود ناموفق بود", "error": detail[-1800:]})
    try:
        data = json.loads(lines[-1])
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"message": "پاسخ Performance معتبر نیست", "error": lines[-1][-1400:]}) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="پاسخ Performance معتبر نیست")
    return data


@router.post("/{node_id}/{tag}/advanced-test")
async def advanced_benchmark_outbound(node_id: int, tag: str, payload: OutboundBenchmarkIn, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    clean_tag = _valid_tag(tag)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        _validate_target(doc, clean_tag)
        baseline = await _run_benchmark(conn, tag=clean_tag, profile=payload.profile, score_profile=payload.score_profile)
        advanced = await _run_advanced_diagnostics(
            conn,
            tag=clean_tag,
            profile=payload.profile,
            idle_latency_ms=baseline.get("latency_ms"),
            baseline_download_mbps=baseline.get("download_mbps"),
        )
        merged = {**baseline, **advanced}
        merged.update(score_benchmark_v262(merged, payload.score_profile))
        await _persist_result(conn, merged)
        return {"node_id": node.id, **merged}
    finally:
        conn.close()
        await conn.wait_closed()


@router.get("/{node_id}/tuning")
async def outbound_tuning_audit(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        return {"node_id": node.id, "node_name": node.name, **(await _run_json_script(conn, _tuning_audit_script(), timeout=45))}
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/tuning/apply")
async def outbound_tuning_apply(node_id: int, payload: TuningApplyIn, db: Session = Depends(get_db)):
    if payload.profile != "bbr_fq":
        raise HTTPException(status_code=409, detail="پروفایل Performance پشتیبانی نمی‌شود")
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        return {"node_id": node.id, "node_name": node.name, "profile": payload.profile, **(await _run_json_script(conn, _tuning_apply_script(), timeout=60))}
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/tuning/rollback")
async def outbound_tuning_rollback(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        return {"node_id": node.id, "node_name": node.name, **(await _run_json_script(conn, _tuning_rollback_script(), timeout=60))}
    finally:
        conn.close()
        await conn.wait_closed()


@router.get("/{node_id}/advanced-state")
async def outbound_advanced_state(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        state = await _read_state(conn)
        return {
            "ok": True,
            "node_id": node.id,
            "node_name": node.name,
            "benchmarkable_tags": _benchmarkable_tags(doc),
            "latest": state.get("latest") or {},
            "history": state.get("history") or {},
            "advanced_metrics": [
                "parallel_download_mbps", "parallel_upload_mbps", "loaded_latency_ms",
                "loaded_jitter_ms", "loaded_probe_loss_pct", "bufferbloat_ms",
                "tls_ms", "ttfb_ms", "http_version",
            ],
            "tuning_profiles": ["bbr_fq"],
            "safety": {
                "production_route_unchanged_during_test": True,
                "live_qdisc_not_replaced": True,
                "automatic_tuning_disabled": True,
            },
        }
    finally:
        conn.close()
        await conn.wait_closed()


__all__ = ["_tuning_apply_script", "_tuning_rollback_script", "router"]
