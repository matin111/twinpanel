from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..node_runtime_connection import connect_protocol_runtime
from .outbound_performance_v261 import _benchmarkable_tags, _persist_result, _read_state, _validate_target
from .outbound_performance_v262 import _tuning_audit_script
from .outbound_performance_v262_runtime import _run_json_script
from .outbound_performance_v265 import _as_float
from .outbound_performance_v268 import (
    OptimizeIn,
    SmartRouteIn,
    _ab_decision,
    _enrich_v4,
    _run_v4_benchmark,
    _smart_score,
    _tuning_apply_v4_script,
    _tuning_rollback_v4_script,
)
from .singbox_outbounds import _apply, _node, _read_document, _valid_tag


router = APIRouter(
    prefix="/v1/settings/vpn/outbound-performance-v4",
    tags=["outbound-performance-v268-guard"],
    dependencies=[Depends(require_admin)],
)


def _v4_tuning_status_script() -> str:
    return r'''from __future__ import annotations
import json
import pathlib
import subprocess

STATE = pathlib.Path("/etc/twinpanel/performance/tcp-accelerator-v4-backup.json")

def sysctl(name):
    proc = subprocess.run(["sysctl", "-n", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    return (proc.stdout or "").strip() if proc.returncode == 0 else None

cc = sysctl("net.ipv4.tcp_congestion_control")
qdisc = sysctl("net.core.default_qdisc")
mtu = sysctl("net.ipv4.tcp_mtu_probing")
backup_available = STATE.is_file() and STATE.stat().st_size > 0
print(json.dumps({
    "v4_backup_available": backup_available,
    "v4_active": bool(backup_available and cc == "bbr" and qdisc == "fq" and mtu == "1"),
    "v4_state_path": str(STATE),
}, ensure_ascii=False))
'''


def _safe_smart_route_decision(
    doc: dict[str, Any],
    latest: dict[str, Any],
    *,
    min_confidence: float,
    min_score_gain: float,
    minimum_candidate_score: float,
) -> dict[str, Any]:
    route = doc.get("route") if isinstance(doc.get("route"), dict) else {}
    current_tag = str(route.get("final") or "direct").strip() or "direct"
    valid_tags = set(_benchmarkable_tags(doc))

    rows: dict[str, dict[str, Any]] = {}
    for raw_tag, raw in latest.items():
        tag = str(raw_tag)
        if tag not in valid_tags or not isinstance(raw, dict):
            continue
        item = _enrich_v4(raw)
        item["smart_score"] = _smart_score(item)
        rows[tag] = item

    eligible: list[tuple[float, str, dict[str, Any]]] = []
    for tag, item in rows.items():
        freshness = (item.get("freshness") or {}).get("state")
        confidence = _as_float(item.get("confidence_score")) or 0.0
        score = _as_float(item.get("score")) or 0.0
        if (
            bool(item.get("ok"))
            and freshness in {"fresh", "recent"}
            and confidence >= min_confidence
            and score >= minimum_candidate_score
        ):
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
            "requires_measured_current": True,
            "inventory_filtered": True,
        },
    }
    if candidate is None:
        return response

    candidate_score, candidate_tag, _candidate_item = candidate
    if candidate_tag == current_tag:
        response["reason"] = "current_is_best"
        return response

    if current is None:
        response["reason"] = "current_unmeasured"
        return response

    current_freshness = (current.get("freshness") or {}).get("state")
    current_confidence = _as_float(current.get("confidence_score")) or 0.0
    current_score = _as_float(current.get("smart_score")) or 0.0
    gain = round(candidate_score - current_score, 2)
    response["score_gain"] = gain

    if current_freshness not in {"fresh", "recent"}:
        response["reason"] = "current_stale_retest"
        return response
    if current_confidence < min_confidence:
        response["reason"] = "current_low_confidence_retest"
        return response
    if not bool(current.get("ok")):
        response["should_switch"] = True
        response["reason"] = "current_failed"
    elif gain >= min_score_gain:
        response["should_switch"] = True
        response["reason"] = "candidate_clears_hysteresis"
    else:
        response["reason"] = "hysteresis_hold"
    return response


@router.get("/{node_id}")
async def outbound_performance_v4_guarded_state(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        state = await _read_state(conn)
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        decision = _safe_smart_route_decision(
            doc,
            latest,
            min_confidence=75.0,
            min_score_gain=6.0,
            minimum_candidate_score=55.0,
        )
        tuning = await _run_json_script(conn, _tuning_audit_script(), timeout=45)
        v4_status = await _run_json_script(conn, _v4_tuning_status_script(), timeout=30)
        return {
            "ok": True,
            "schema": 4,
            "node_id": node.id,
            "node_name": node.name,
            "benchmarkable_tags": _benchmarkable_tags(doc),
            "smart_route": decision,
            "tuning": {**tuning, **v4_status},
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
                "smart_route_current_measurement_required": True,
                "http3_over_socks_claimed": False,
            },
            "semantics": {
                "packet_loss": "application_probe_loss_not_udp_or_icmp_packet_loss",
                "plpmtud": "tcp_mtu_probing_1_only_after_detected_blackhole",
                "smart_route": "explicit_apply_only_no_background_route_flapping",
                "live_qdisc": "not_replaced",
                "ab_optimizer": "requires_clean_v4_baseline_state",
            },
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/smart-route")
async def outbound_smart_route_guarded(node_id: int, payload: SmartRouteIn, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        state = await _read_state(conn)
        latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        decision = _safe_smart_route_decision(
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


@router.post("/{node_id}/{tag}/ab-optimize")
async def outbound_ab_optimize_guarded(
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
        status = await _run_json_script(conn, _v4_tuning_status_script(), timeout=30)
        if bool(status.get("v4_backup_available")):
            raise HTTPException(
                status_code=409,
                detail="V4 tuning is already active or has a rollback state; rollback v4 tuning before running a new A/B baseline",
            )

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


__all__ = ["_safe_smart_route_decision", "_v4_tuning_status_script", "router"]
