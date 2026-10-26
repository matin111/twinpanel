from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
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
from .outbound_performance_v262 import _run_advanced_diagnostics, score_benchmark_v262
from .singbox_outbounds import _node, _read_document, _valid_tag


router = APIRouter(
    prefix="/v1/settings/vpn/outbound-performance-lab",
    tags=["outbound-performance-v265"],
    dependencies=[Depends(require_admin)],
)


# Upper bounds are payload budgets, not promises about wire bytes. The loaded
# phase is intentionally bounded so a full benchmark cannot consume unlimited
# traffic when the path is very fast.
_PROFILE_BUDGETS: dict[str, dict[str, int]] = {
    "quick": {
        "baseline_download_bytes": 1_000_000,
        "baseline_upload_bytes": 500_000,
        "parallel_download_bytes": 1_000_000,
        "parallel_upload_bytes": 500_000,
        "loaded_download_cap_bytes": 5_000_000,
        "idle_samples": 4,
        "loaded_samples": 2,
        "parallel_streams": 1,
    },
    "standard": {
        "baseline_download_bytes": 16_000_000,
        "baseline_upload_bytes": 6_000_000,
        "parallel_download_bytes": 10_000_000,
        "parallel_upload_bytes": 4_000_000,
        "loaded_download_cap_bytes": 50_000_000,
        "idle_samples": 6,
        "loaded_samples": 5,
        "parallel_streams": 2,
    },
    "full": {
        "baseline_download_bytes": 41_000_000,
        "baseline_upload_bytes": 16_000_000,
        "parallel_download_bytes": 40_000_000,
        "parallel_upload_bytes": 20_000_000,
        "loaded_download_cap_bytes": 100_000_000,
        "idle_samples": 8,
        "loaded_samples": 8,
        "parallel_streams": 4,
    },
}


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _values(raw: Any) -> list[float]:
    if not isinstance(raw, list):
        return []
    values: list[float] = []
    for item in raw:
        number = _as_float(item)
        if number is not None and number >= 0:
            values.append(number)
    return values


def _percentile(raw: Any, q: float) -> float | None:
    values = sorted(_values(raw))
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    position = max(0.0, min(1.0, q)) * (len(values) - 1)
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return round(values[low], 2)
    fraction = position - low
    return round(values[low] + (values[high] - values[low]) * fraction, 2)


def _profile_budget(profile: str) -> dict[str, Any]:
    name = profile if profile in _PROFILE_BUDGETS else "standard"
    raw = dict(_PROFILE_BUDGETS[name])
    download = raw["baseline_download_bytes"] + raw["parallel_download_bytes"] + raw["loaded_download_cap_bytes"]
    upload = raw["baseline_upload_bytes"] + raw["parallel_upload_bytes"]
    payload = download + upload
    # TLS/HTTP headers and the tiny zero-byte probes are deliberately expressed
    # as an estimate instead of being presented as exact accounting.
    wire_estimate = int(math.ceil(payload * 1.03))
    return {
        "profile": name,
        **raw,
        "payload_download_upper_bound_bytes": download,
        "payload_upload_upper_bound_bytes": upload,
        "payload_total_upper_bound_bytes": payload,
        "estimated_wire_upper_bound_bytes": wire_estimate,
        "payload_total_upper_bound_mib": round(payload / 1024 / 1024, 1),
        "estimated_wire_upper_bound_mib": round(wire_estimate / 1024 / 1024, 1),
    }


def _stability_score(result: dict[str, Any]) -> float:
    idle = _values(result.get("latency_samples_ms"))
    loaded = _values(result.get("loaded_latency_samples_ms"))
    jitter = max(_as_float(result.get("jitter_ms")) or 0.0, _as_float(result.get("loaded_jitter_ms")) or 0.0)
    loss = max(_as_float(result.get("probe_loss_pct")) or 0.0, _as_float(result.get("loaded_probe_loss_pct")) or 0.0)
    idle_p50 = _percentile(idle, 0.50)
    idle_p95 = _percentile(idle, 0.95)
    loaded_p50 = _percentile(loaded, 0.50)
    loaded_p95 = _percentile(loaded, 0.95)

    idle_spread = max(0.0, (idle_p95 or 0.0) - (idle_p50 or 0.0))
    loaded_spread = max(0.0, (loaded_p95 or 0.0) - (loaded_p50 or 0.0))
    penalty = (
        min(32.0, loss * 2.2)
        + min(24.0, jitter * 1.2)
        + min(18.0, idle_spread * 0.45)
        + min(18.0, loaded_spread * 0.22)
    )
    return round(max(0.0, min(100.0, 100.0 - penalty)), 1)


def _confidence_score(result: dict[str, Any], profile: str) -> float:
    budget = _profile_budget(profile)
    expected_idle = max(1, int(budget["idle_samples"]))
    expected_loaded = max(1, int(budget["loaded_samples"]))
    idle_coverage = min(1.0, len(_values(result.get("latency_samples_ms"))) / expected_idle)
    loaded_coverage = min(1.0, len(_values(result.get("loaded_latency_samples_ms"))) / expected_loaded)
    throughput_signals = sum(
        1
        for key in ("download_mbps", "upload_mbps", "parallel_download_mbps", "parallel_upload_mbps")
        if (_as_float(result.get(key)) or 0.0) > 0
    )
    throughput_coverage = throughput_signals / 4.0
    route_coverage = 1.0 if bool(result.get("ok")) else 0.0
    advanced_coverage = 1.0 if bool(result.get("advanced_ok")) else 0.0
    score = 100.0 * (
        idle_coverage * 0.30
        + loaded_coverage * 0.20
        + throughput_coverage * 0.25
        + route_coverage * 0.15
        + advanced_coverage * 0.10
    )
    return round(max(0.0, min(100.0, score)), 1)


def _freshness(tested_at: Any) -> dict[str, Any]:
    raw = str(tested_at or "").strip()
    if not raw:
        return {"state": "unknown", "age_seconds": None}
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()))
    except Exception:
        return {"state": "unknown", "age_seconds": None}
    state = "fresh" if age <= 1800 else "recent" if age <= 21600 else "stale"
    return {"state": state, "age_seconds": age}


def _enrich_result(result: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(result)
    profile = str(enriched.get("profile") or "standard")
    budget = _profile_budget(profile)

    idle_p50 = _percentile(enriched.get("latency_samples_ms"), 0.50)
    idle_p95 = _percentile(enriched.get("latency_samples_ms"), 0.95)
    loaded_p50 = _percentile(enriched.get("loaded_latency_samples_ms"), 0.50)
    loaded_p95 = _percentile(enriched.get("loaded_latency_samples_ms"), 0.95)
    stability = _stability_score(enriched)
    confidence = _confidence_score(enriched, profile)

    measured_download = _as_int(enriched.get("download_bytes")) + _as_int(enriched.get("parallel_download_bytes"))
    measured_upload = _as_int(enriched.get("upload_bytes")) + _as_int(enriched.get("parallel_upload_bytes"))
    measured_payload = measured_download + measured_upload

    previous_score = _as_float(enriched.get("score_v2"))
    if previous_score is None:
        previous_score = _as_float(enriched.get("score")) or 0.0
    if bool(enriched.get("ok")):
        quality_score = (previous_score * 0.82 + stability * 0.18) * (0.80 + 0.20 * confidence / 100.0)
        score = round(max(0.0, min(100.0, quality_score)), 1)
        quality = "excellent" if score >= 85 else "good" if score >= 70 else "fair" if score >= 50 else "poor"
    else:
        score = 0.0
        quality = "failed"

    freshness = _freshness(enriched.get("tested_at") or enriched.get("advanced_tested_at"))
    enriched.update(
        {
            "score_v2": round(previous_score, 1),
            "score": score,
            "score_version": 3,
            "quality": quality,
            "latency_p50_ms": idle_p50,
            "latency_p95_ms": idle_p95,
            "loaded_latency_p50_ms": loaded_p50,
            "loaded_latency_p95_ms": loaded_p95,
            "stability_score": stability,
            "confidence_score": confidence,
            "confidence_level": "high" if confidence >= 85 else "medium" if confidence >= 60 else "low",
            "freshness": freshness,
            "transfer": {
                "measured_download_bytes": measured_download,
                "measured_upload_bytes": measured_upload,
                "measured_payload_bytes": measured_payload,
                "measured_payload_mib": round(measured_payload / 1024 / 1024, 1),
                "loaded_phase_is_bounded_but_not_byte_metered": True,
                "loaded_download_cap_bytes": budget["loaded_download_cap_bytes"],
                "payload_total_upper_bound_bytes": budget["payload_total_upper_bound_bytes"],
                "payload_total_upper_bound_mib": budget["payload_total_upper_bound_mib"],
                "estimated_wire_upper_bound_bytes": budget["estimated_wire_upper_bound_bytes"],
                "estimated_wire_upper_bound_mib": budget["estimated_wire_upper_bound_mib"],
            },
        }
    )
    return enriched


def _metric_item(item: dict[str, Any], metric: str) -> dict[str, Any]:
    return {
        "tag": item.get("tag"),
        "score": item.get("score"),
        "stability_score": item.get("stability_score"),
        "confidence_score": item.get("confidence_score"),
        "metric": metric,
        "value": item.get(metric),
        "freshness": item.get("freshness"),
    }


def _recommendations(latest: dict[str, Any]) -> dict[str, Any]:
    enriched = [_enrich_result(value) for value in latest.values() if isinstance(value, dict)]
    eligible = [item for item in enriched if bool(item.get("ok"))]
    if not eligible:
        return {
            "source": "none",
            "best_overall": None,
            "lowest_latency": None,
            "best_download": None,
            "best_upload": None,
            "most_stable": None,
            "lowest_bufferbloat": None,
        }
    fresh = [item for item in eligible if (item.get("freshness") or {}).get("state") != "stale"]
    pool = fresh or eligible

    def best_max(metric: str, fallback: str | None = None) -> dict[str, Any] | None:
        candidates = []
        for item in pool:
            value = _as_float(item.get(metric))
            if value is None and fallback:
                value = _as_float(item.get(fallback))
            if value is not None:
                candidates.append((value, item))
        if not candidates:
            return None
        _, item = max(candidates, key=lambda pair: pair[0])
        return _metric_item(item, metric)

    def best_min(metric: str, fallback: str | None = None) -> dict[str, Any] | None:
        candidates = []
        for item in pool:
            value = _as_float(item.get(metric))
            if value is None and fallback:
                value = _as_float(item.get(fallback))
            if value is not None:
                candidates.append((value, item))
        if not candidates:
            return None
        _, item = min(candidates, key=lambda pair: pair[0])
        return _metric_item(item, metric)

    # Use the best of serial/parallel throughput for capacity recommendations.
    for item in pool:
        item["effective_download_mbps"] = max(_as_float(item.get("download_mbps")) or 0.0, _as_float(item.get("parallel_download_mbps")) or 0.0) or None
        item["effective_upload_mbps"] = max(_as_float(item.get("upload_mbps")) or 0.0, _as_float(item.get("parallel_upload_mbps")) or 0.0) or None

    return {
        "source": "fresh_or_recent" if fresh else "stale_fallback",
        "best_overall": best_max("score"),
        "lowest_latency": best_min("latency_p95_ms", "latency_ms"),
        "best_download": best_max("effective_download_mbps"),
        "best_upload": best_max("effective_upload_mbps"),
        "most_stable": best_max("stability_score"),
        "lowest_bufferbloat": best_min("bufferbloat_ms"),
    }


def _profile_catalog() -> list[dict[str, Any]]:
    return [_profile_budget(name) for name in ("quick", "standard", "full")]


@router.get("/profiles")
async def outbound_performance_profiles():
    return {
        "ok": True,
        "profiles": _profile_catalog(),
        "target_policy": {
            "provider": "Cloudflare Speed Test",
            "origin": "https://speed.cloudflare.com",
            "user_supplied_url_allowed": False,
            "reason": "fixed_server_controlled_target_prevents_ssrf",
        },
        "semantics": {
            "probe_loss": "application_probe_loss_not_icmp_packet_loss",
            "throughput": "real_http_payload_through_selected_outbound",
            "wire_bytes": "estimated_upper_bound_not_exact_accounting",
            "routing": "benchmark_never_auto_changes_production_route",
        },
    }


@router.get("/{node_id}")
async def outbound_performance_lab_state(node_id: int, db: Session = Depends(get_db)):
    node = _node(db, node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        doc = await _read_document(conn)
        state = await _read_state(conn)
        raw_latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
        latest = {str(tag): _enrich_result(value) for tag, value in raw_latest.items() if isinstance(value, dict)}
        ranking = sorted(
            latest.values(),
            key=lambda item: (bool(item.get("ok")), float(item.get("score") or 0.0), float(item.get("confidence_score") or 0.0)),
            reverse=True,
        )
        return {
            "ok": True,
            "schema": 3,
            "node_id": node.id,
            "node_name": node.name,
            "benchmarkable_tags": _benchmarkable_tags(doc),
            "profiles": _profile_catalog(),
            "score_profiles": ["balanced", "latency", "download", "upload", "stability"],
            "latest": latest,
            "ranking": ranking,
            "recommendations": _recommendations(raw_latest),
            "updated_at": state.get("updated_at"),
            "safety": {
                "production_route_unchanged_during_test": True,
                "automatic_route_switch_disabled": True,
                "user_supplied_test_url_allowed": False,
                "tp27_vxlan_untouched": True,
            },
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/{node_id}/{tag}/test")
async def benchmark_outbound_v265(
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
        baseline = await _run_benchmark(
            conn,
            tag=clean_tag,
            profile=payload.profile,
            score_profile=payload.score_profile,
        )
        advanced = await _run_advanced_diagnostics(
            conn,
            tag=clean_tag,
            profile=payload.profile,
            idle_latency_ms=baseline.get("latency_ms"),
            baseline_download_mbps=baseline.get("download_mbps"),
        )
        merged = {**baseline, **advanced}
        merged.update(score_benchmark_v262(merged, payload.score_profile))
        enriched = _enrich_result(merged)
        await _persist_result(conn, enriched)
        return {"node_id": node.id, **enriched}
    finally:
        conn.close()
        await conn.wait_closed()


__all__ = [
    "_PROFILE_BUDGETS",
    "_confidence_score",
    "_enrich_result",
    "_percentile",
    "_profile_budget",
    "_recommendations",
    "_stability_score",
    "router",
]
