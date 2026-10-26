from __future__ import annotations

import base64
import json
import math
import shlex
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..node_runtime_connection import connect_protocol_runtime
from .outbound_performance_v261 import (
    BenchmarkProfile,
    OutboundBenchmarkIn,
    _benchmarkable_tags,
    _persist_result,
    _read_state,
    _run_benchmark,
    _validate_target,
)
from .outbound_performance_v262 import (
    _run_advanced_diagnostics,
    _tuning_audit_script,
    score_benchmark_v262,
)
from .outbound_performance_v262_runtime import _run_json_script
from .outbound_performance_v265 import _as_float, _enrich_result
from .singbox_outbounds import _apply, _node, _read_document, _valid_tag


router = APIRouter(
    prefix="/v1/settings/vpn/outbound-performance-v4",
    tags=["outbound-performance-v268"],
    dependencies=[Depends(require_admin)],
)

ScoreProfile = Literal["balanced", "latency", "download", "upload", "stability"]


class SmartRouteIn(BaseModel):
    apply: bool = False
    min_confidence: float = Field(default=75.0, ge=50.0, le=100.0)
    min_score_gain: float = Field(default=6.0, ge=1.0, le=30.0)
    minimum_candidate_score: float = Field(default=55.0, ge=20.0, le=95.0)


class OptimizeIn(BaseModel):
    profile: BenchmarkProfile = "standard"
    score_profile: ScoreProfile = "balanced"
    auto_rollback: bool = True
    min_score_gain: float = Field(default=2.0, ge=0.0, le=20.0)
    min_throughput_gain_pct: float = Field(default=5.0, ge=0.0, le=100.0)
    max_loaded_latency_regression_pct: float = Field(default=25.0, ge=0.0, le=200.0)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _ratio_score(value: float | None, target: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return _clamp(100.0 * math.log1p(float(value)) / math.log1p(float(target)))


def _effective(result: dict[str, Any], primary: str, parallel: str) -> float | None:
    value = max(_as_float(result.get(primary)) or 0.0, _as_float(result.get(parallel)) or 0.0)
    return round(value, 2) if value > 0 else None


def _latency_score(value: float | None, *, ideal: float, slope: float) -> float:
    if value is None:
        return 0.0
    return _clamp(100.0 - max(0.0, float(value) - ideal) * slope)


def _loss_score(value: float | None) -> float:
    if value is None:
        return 0.0
    return _clamp(100.0 - float(value) * 5.0)


def _use_case_scores(result: dict[str, Any]) -> dict[str, float]:
    download = _effective(result, "download_mbps", "parallel_download_mbps")
    upload = _effective(result, "upload_mbps", "parallel_upload_mbps")
    idle_p95 = _as_float(result.get("latency_p95_ms")) or _as_float(result.get("latency_ms"))
    loaded_p95 = _as_float(result.get("loaded_latency_p95_ms")) or _as_float(result.get("loaded_latency_ms"))
    jitter = max(_as_float(result.get("jitter_ms")) or 0.0, _as_float(result.get("loaded_jitter_ms")) or 0.0)
    loss = max(_as_float(result.get("probe_loss_pct")) or 0.0, _as_float(result.get("loaded_probe_loss_pct")) or 0.0)
    stability = _as_float(result.get("stability_score")) or 0.0
    confidence = _as_float(result.get("confidence_score")) or 0.0

    idle = _latency_score(idle_p95, ideal=20.0, slope=0.75)
    loaded = _latency_score(loaded_p95, ideal=45.0, slope=0.45)
    jitter_score = _clamp(100.0 - jitter * 4.0)
    loss_score = _loss_score(loss)
    down_score = _ratio_score(download, 200.0)
    up_score = _ratio_score(upload, 100.0)

    realtime = idle * 0.30 + loaded * 0.25 + jitter_score * 0.20 + loss_score * 0.10 + stability * 0.15
    streaming = down_score * 0.50 + loaded * 0.15 + stability * 0.20 + confidence * 0.15
    bulk = down_score * 0.55 + up_score * 0.20 + stability * 0.10 + confidence * 0.15
    upload_backup = up_score * 0.60 + loaded * 0.15 + stability * 0.10 + confidence * 0.15
    balanced = (
        realtime * 0.25
        + streaming * 0.25
        + bulk * 0.30
        + upload_backup * 0.20
    )
    return {
        "balanced": round(_clamp(balanced), 1),
        "realtime": round(_clamp(realtime), 1),
        "streaming": round(_clamp(streaming), 1),
        "bulk": round(_clamp(bulk), 1),
        "upload_backup": round(_clamp(upload_backup), 1),
    }


def _bufferbloat_grade(value: float | None) -> str:
    if value is None:
        return "unknown"
    delay = max(0.0, float(value))
    if delay <= 5:
        return "A+"
    if delay <= 15:
        return "A"
    if delay <= 30:
        return "B"
    if delay <= 60:
        return "C"
    if delay <= 100:
        return "D"
    return "F"


def _enrich_v4(result: dict[str, Any]) -> dict[str, Any]:
    enriched = _enrich_result(result)
    download = _effective(enriched, "download_mbps", "parallel_download_mbps")
    upload = _effective(enriched, "upload_mbps", "parallel_upload_mbps")
    serial_down = _as_float(enriched.get("download_mbps"))
    parallel_down = _as_float(enriched.get("parallel_download_mbps"))
    serial_up = _as_float(enriched.get("upload_mbps"))
    parallel_up = _as_float(enriched.get("parallel_upload_mbps"))
    down_gain = None if not serial_down or not parallel_down else round(parallel_down / serial_down, 2)
    up_gain = None if not serial_up or not parallel_up else round(parallel_up / serial_up, 2)
    asymmetry = None
    if download and upload:
        asymmetry = round(max(download, upload) / max(0.01, min(download, upload)), 2)
    enriched.update(
        {
            "score_version": 4,
            "effective_download_mbps": download,
            "effective_upload_mbps": upload,
            "parallel_download_gain_ratio": down_gain,
            "parallel_upload_gain_ratio": up_gain,
            "throughput_asymmetry_ratio": asymmetry,
            "bufferbloat_grade": _bufferbloat_grade(_as_float(enriched.get("bufferbloat_ms"))),
            "use_case_scores": _use_case_scores(enriched),
        }
    )
    return enriched


def _smart_score(result: dict[str, Any]) -> float:
    score = _as_float(result.get("score")) or 0.0
    stability = _as_float(result.get("stability_score")) or 0.0
    confidence = _as_float(result.get("confidence_score")) or 0.0
    return round(score * 0.70 + stability * 0.20 + confidence * 0.10, 2)


def _smart_route_decision(
    doc: dict[str, Any],
    latest: dict[str, Any],
    *,
    min_confidence: float,
    min_score_gain: float,
    minimum_candidate_score: float,
) -> dict[str, Any]:
    route = doc.get("route") if isinstance(doc.get("route"), dict) else {}
    current_tag = str(route.get("final") or "direct").strip() or "direct"
    rows: dict[str, dict[str, Any]] = {}
    for tag, raw in latest.items():
        if not isinstance(raw, dict):
            continue
        item = _enrich_v4(raw)
        item["smart_score"] = _smart_score(item)
        rows[str(tag)] = item

    eligible = []
    for tag, item in rows.items():
        freshness = (item.get("freshness") or {}).get("state")
        confidence = _as_float(item.get("confidence_score")) or 0.0
        score = _as_float(item.get("score")) or 0.0
        if bool(item.get("ok")) and freshness in {"fresh", "recent"} and confidence >= min_confidence and score >= minimum_candidate_score:
            eligible.append((float(item.get("smart_score") or 0.0), tag, item))
    eligible.sort(reverse=True, key=lambda row: row[0])

    current = rows.get(current_tag)
    candidate = eligible[0] if eligible else None
    response: dict[str, Any] = {
        "current_tag": current_tag,
        "current": current,
        "candidate_tag": candidate[1] if candidate else None,
        "candidate": candidate[2] if candidate else None,
        "should_switch": False,
        "reason": "no_eligible_candidate" if candidate is None else "hold",
        "score_gain": None,
        "guard": {
            "min_confidence": min_confidence,
            "min_score_gain": min_score_gain,
            "minimum_candidate_score": minimum_candidate_score,
            "requires_fresh_or_recent": True,
        },
    }
    if candidate is None:
        return response
    candidate_score, candidate_tag, candidate_item = candidate
    if candidate_tag == current_tag:
        response["reason"] = "current_is_best"
        return response

    current_ok = bool(current and current.get("ok"))
    current_freshness = (current.get("freshness") or {}).get("state") if current else None
    current_confidence = _as_float(current.get("confidence_score")) or 0.0 if current else 0.0
    current_score = _as_float(current.get("smart_score")) or 0.0 if current else 0.0
    gain = round(candidate_score - current_score, 2)
    response["score_gain"] = gain

    if not current_ok or current_freshness == "stale" or current_confidence < min_confidence:
        response["should_switch"] = True
        response["reason"] = "current_unhealthy_or_untrusted"
    elif gain >= min_score_gain:
        response["should_switch"] = True
        response["reason"] = "candidate_clears_hysteresis"
    else:
        response["reason"] = "hysteresis_hold"
    return response


def _tuning_apply_v4_script() -> str:
    return r'''from __future__ import annotations
import base64
import json
import pathlib
import shutil
import subprocess

STATE = pathlib.Path("/etc/twinpanel/performance/tcp-accelerator-v4-backup.json")
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
    "tcp_mtu_probing": sysctl("net.ipv4.tcp_mtu_probing"),
    "profile_existed": PROFILE.exists(),
    "profile_b64": base64.b64encode(previous_profile).decode("ascii") if previous_profile is not None else None,
}
if not STATE.exists():
    tmp = STATE.with_suffix(".json.new")
    tmp.write_text(json.dumps(backup, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(STATE)
if shutil.which("modprobe"):
    run(["modprobe", "tcp_bbr"])
    run(["modprobe", "sch_fq"])
available = (sysctl("net.ipv4.tcp_available_congestion_control") or "").split()
if "bbr" not in available:
    raise RuntimeError("bbr_unavailable_on_kernel")

def restore_runtime():
    if backup.get("tcp_congestion_control"):
        run(["sysctl", "-w", "net.ipv4.tcp_congestion_control=" + str(backup["tcp_congestion_control"])])
    if backup.get("default_qdisc"):
        run(["sysctl", "-w", "net.core.default_qdisc=" + str(backup["default_qdisc"])])
    if backup.get("tcp_mtu_probing") is not None:
        run(["sysctl", "-w", "net.ipv4.tcp_mtu_probing=" + str(backup["tcp_mtu_probing"])])
    if backup.get("profile_existed"):
        raw = base64.b64decode(str(backup.get("profile_b64") or ""))
        tmp = PROFILE.with_suffix(".conf.restore")
        tmp.write_bytes(raw)
        tmp.chmod(0o644)
        tmp.replace(PROFILE)
    else:
        try: PROFILE.unlink()
        except FileNotFoundError: pass

try:
    profile_text = (
        "# Managed by TwinPanel Outbound Performance Lab v4\n"
        "net.ipv4.tcp_congestion_control=bbr\n"
        "net.core.default_qdisc=fq\n"
        "net.ipv4.tcp_mtu_probing=1\n"
    )
    tmp_profile = PROFILE.with_suffix(".conf.new")
    tmp_profile.write_text(profile_text, encoding="utf-8")
    tmp_profile.chmod(0o644)
    tmp_profile.replace(PROFILE)
    run(["sysctl", "-w", "net.ipv4.tcp_congestion_control=bbr"], check=True)
    run(["sysctl", "-w", "net.core.default_qdisc=fq"], check=True)
    run(["sysctl", "-w", "net.ipv4.tcp_mtu_probing=1"], check=True)
except Exception:
    restore_runtime()
    raise

print(json.dumps({
    "ok": True,
    "profile": "bbr_fq_plpmtud",
    "tcp_congestion_control": sysctl("net.ipv4.tcp_congestion_control"),
    "default_qdisc": sysctl("net.core.default_qdisc"),
    "tcp_mtu_probing": sysctl("net.ipv4.tcp_mtu_probing"),
    "live_qdisc_replaced": False,
    "note": "BBR affects new TCP connections; tcp_mtu_probing=1 activates probing only after a detected PMTU black hole.",
}, ensure_ascii=False))
'''


def _tuning_rollback_v4_script() -> str:
    return r'''from __future__ import annotations
import base64
import json
import pathlib
import subprocess

STATE = pathlib.Path("/etc/twinpanel/performance/tcp-accelerator-v4-backup.json")
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
    raise RuntimeError("tuning_v4_backup_not_found")
backup = json.loads(STATE.read_text(encoding="utf-8"))
if backup.get("profile_existed"):
    raw = base64.b64decode(str(backup.get("profile_b64") or ""))
    tmp = PROFILE.with_suffix(".conf.rollback")
    tmp.write_bytes(raw)
    tmp.chmod(0o644)
    tmp.replace(PROFILE)
else:
    try: PROFILE.unlink()
    except FileNotFoundError: pass
for key, sysctl_name in (
    ("tcp_congestion_control", "net.ipv4.tcp_congestion_control"),
    ("default_qdisc", "net.core.default_qdisc"),
    ("tcp_mtu_probing", "net.ipv4.tcp_mtu_probing"),
):
    value = backup.get(key)
    if value is not None and str(value).strip():
        run(["sysctl", "-w", f"{sysctl_name}={value}"], check=True)
STATE.unlink()
print(json.dumps({
    "ok": True,
    "tcp_congestion_control": sysctl("net.ipv4.tcp_congestion_control"),
    "default_qdisc": sysctl("net.core.default_qdisc"),
    "tcp_mtu_probing": sysctl("net.ipv4.tcp_mtu_probing"),
    "live_qdisc_replaced": False,
}, ensure_ascii=False))
'''


async def _run_v4_benchmark(conn, *, tag: str, profile: BenchmarkProfile, score_profile: ScoreProfile) -> dict[str, Any]:
    baseline = await _run_benchmark(conn, tag=tag, profile=profile, score_profile=score_profile)
    advanced = await _run_advanced_diagnostics(
        conn,
        tag=tag,
        profile=profile,
        idle_latency_ms=baseline.get("latency_ms"),
        baseline_download_mbps=baseline.get("download_mbps"),
    )
    merged = {**baseline, **advanced}
    merged.update(score_benchmark_v262(merged, score_profile))
    return _enrich_v4(merged)


def _pct_gain(before: float | None, after: float | None) -> float | None:
    if before is None or before <= 0 or after is None:
        return None
    return round((after - before) * 100.0 / before, 2)


def _ab_decision(baseline: dict[str, Any], tuned: dict[str, Any], payload: OptimizeIn) -> dict[str, Any]:
    baseline_score = _as_float(baseline.get("score")) or 0.0
    tuned_score = _as_float(tuned.get("score")) or 0.0
    baseline_down = _as_float(baseline.get("effective_download_mbps"))
    tuned_down = _as_float(tuned.get("effective_download_mbps"))
    baseline_up = _as_float(baseline.get("effective_upload_mbps"))
    tuned_up = _as_float(tuned.get("effective_upload_mbps"))
    down_gain = _pct_gain(baseline_down, tuned_down)
    up_gain = _pct_gain(baseline_up, tuned_up)
    base_loaded = _as_float(baseline.get("loaded_latency_p95_ms")) or _as_float(baseline.get("loaded_latency_ms"))
    tuned_loaded = _as_float(tuned.get("loaded_latency_p95_ms")) or _as_float(tuned.get("loaded_latency_ms"))
    latency_regression = _pct_gain(base_loaded, tuned_loaded)
    base_loss = max(_as_float(baseline.get("probe_loss_pct")) or 0.0, _as_float(baseline.get("loaded_probe_loss_pct")) or 0.0)
    tuned_loss = max(_as_float(tuned.get("probe_loss_pct")) or 0.0, _as_float(tuned.get("loaded_probe_loss_pct")) or 0.0)
    score_gain = round(tuned_score - baseline_score, 2)
    throughput_gain = max(down_gain or -999.0, up_gain or -999.0)
    latency_ok = latency_regression is None or latency_regression <= payload.max_loaded_latency_regression_pct
    loss_ok = tuned_loss <= base_loss + 2.0
    improved = score_gain >= payload.min_score_gain or throughput_gain >= payload.min_throughput_gain_pct
    keep = bool(tuned.get("ok")) and improved and latency_ok and loss_ok
    return {
        "keep_tuning": keep,
        "score_gain": score_gain,
        "download_gain_pct": down_gain,
        "upload_gain_pct": up_gain,
        "loaded_latency_regression_pct": latency_regression,
        "probe_loss_delta_pct": round(tuned_loss - base_loss, 2),
        "reason": "measured_improvement" if keep else "no_safe_measured_gain",
    }


@router.get("/{node_id}")
async def outbound_performance_v4_state(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        state = await _read_state(conn)
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        decision = _smart_route_decision(
            doc,
            latest,
            min_confidence=75.0,
            min_score_gain=6.0,
            minimum_candidate_score=55.0,
        )
        tuning = await _run_json_script(conn, _tuning_audit_script(), timeout=45)
        return {
            "ok": True,
            "schema": 4,
            "node_id": node.id,
            "node_name": node.name,
            "benchmarkable_tags": _benchmarkable_tags(doc),
            "smart_route": decision,
            "tuning": tuning,
            "capabilities": {
                "real_http_download_upload": True,
                "parallel_throughput": True,
                "idle_loaded_latency": True,
                "p50_p95": True,
                "bufferbloat": True,
                "application_probe_loss": True,
                "ab_optimizer": True,
                "safe_plpmtud": True,
                "smart_route_hysteresis": True,
                "http3_over_socks_claimed": False,
            },
            "semantics": {
                "packet_loss": "application_probe_loss_not_udp_or_icmp_packet_loss",
                "plpmtud": "tcp_mtu_probing_1_only_after_detected_blackhole",
                "smart_route": "explicit_apply_only_no_background_route_flapping",
                "live_qdisc": "not_replaced",
            },
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/smart-route")
async def outbound_smart_route(node_id: int, payload: SmartRouteIn, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        state = await _read_state(conn)
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        decision = _smart_route_decision(
            doc,
            latest,
            min_confidence=payload.min_confidence,
            min_score_gain=payload.min_score_gain,
            minimum_candidate_score=payload.minimum_candidate_score,
        )
        applied = False
        if payload.apply and decision.get("should_switch") and decision.get("candidate_tag"):
            tag = _valid_tag(str(decision["candidate_tag"]))
            await _apply(conn, action="default", tag=tag)
            applied = True
        fresh = await _read_document(conn)
        route = fresh.get("route") if isinstance(fresh.get("route"), dict) else {}
        return {
            "ok": True,
            "node_id": node.id,
            "applied": applied,
            "default_tag": str(route.get("final") or "direct"),
            **decision,
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/tuning/apply")
async def outbound_tuning_apply_v4(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        return {
            "node_id": node.id,
            "node_name": node.name,
            **(await _run_json_script(conn, _tuning_apply_v4_script(), timeout=60)),
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/tuning/rollback")
async def outbound_tuning_rollback_v4(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        return {
            "node_id": node.id,
            "node_name": node.name,
            **(await _run_json_script(conn, _tuning_rollback_v4_script(), timeout=60)),
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/{tag}/ab-optimize")
async def outbound_ab_optimize(
    node_id: int,
    tag: str,
    payload: OptimizeIn,
    db: Session = Depends(get_db),
):
    node = _node(db, node_id)
    clean_tag = _valid_tag(tag)
    conn = await connect_protocol_runtime(node, db)
    tuning_applied = False
    try:
        doc = await _read_document(conn)
        _validate_target(doc, clean_tag)
        baseline = await _run_v4_benchmark(
            conn,
            tag=clean_tag,
            profile=payload.profile,
            score_profile=payload.score_profile,
        )
        if not bool(baseline.get("ok")):
            raise HTTPException(status_code=409, detail="Baseline Outbound benchmark failed; tuning was not changed")
        tuning = await _run_json_script(conn, _tuning_apply_v4_script(), timeout=60)
        tuning_applied = True
        tuned = await _run_v4_benchmark(
            conn,
            tag=clean_tag,
            profile=payload.profile,
            score_profile=payload.score_profile,
        )
        decision = _ab_decision(baseline, tuned, payload)
        rolled_back = False
        if payload.auto_rollback and not decision["keep_tuning"]:
            await _run_json_script(conn, _tuning_rollback_v4_script(), timeout=60)
            tuning_applied = False
            rolled_back = True
            baseline["ab_variant"] = "effective_after_rollback"
            await _persist_result(conn, baseline)
        else:
            tuned["ab_variant"] = "tuned_kept" if decision["keep_tuning"] else "tuned_manual_review"
            await _persist_result(conn, tuned)
        return {
            "ok": True,
            "node_id": node.id,
            "tag": clean_tag,
            "baseline": baseline,
            "tuned": tuned,
            "decision": decision,
            "tuning": tuning,
            "rolled_back": rolled_back,
            "effective_tuning_active": tuning_applied,
        }
    except Exception:
        if tuning_applied and payload.auto_rollback:
            try:
                await _run_json_script(conn, _tuning_rollback_v4_script(), timeout=60)
            except Exception:
                pass
        raise
    finally:
        conn.close()
        await conn.wait_closed()


__all__ = [
    "_ab_decision",
    "_enrich_v4",
    "_smart_route_decision",
    "_tuning_apply_v4_script",
    "_tuning_rollback_v4_script",
    "_use_case_scores",
    "router",
]
