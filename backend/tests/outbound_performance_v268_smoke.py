from __future__ import annotations

from app.routers.outbound_performance_v268 import (
    OptimizeIn,
    _ab_decision,
    _enrich_v4,
    _smart_route_decision,
    _tuning_apply_v4_script,
    _tuning_rollback_v4_script,
    _use_case_scores,
)


def sample(*, tag: str, score: float, confidence: float = 90.0, stability: float = 90.0, ok: bool = True):
    return {
        "ok": ok,
        "tag": tag,
        "profile": "standard",
        "score": score,
        "score_v2": score,
        "quality": "good",
        "tested_at": "2099-01-01T00:00:00+00:00",
        "latency_ms": 28.0,
        "latency_samples_ms": [26.0, 27.0, 28.0, 29.0, 31.0, 33.0],
        "loaded_latency_ms": 45.0,
        "loaded_latency_samples_ms": [42.0, 44.0, 45.0, 47.0, 50.0],
        "jitter_ms": 2.0,
        "loaded_jitter_ms": 3.0,
        "probe_loss_pct": 0.0,
        "loaded_probe_loss_pct": 0.0,
        "download_mbps": 120.0,
        "parallel_download_mbps": 180.0,
        "upload_mbps": 60.0,
        "parallel_upload_mbps": 82.0,
        "bufferbloat_ms": 17.0,
        "advanced_ok": True,
        "stability_score": stability,
        "confidence_score": confidence,
    }


def main() -> None:
    enriched = _enrich_v4(sample(tag="ext-a", score=82.0))
    assert enriched["score_version"] == 4
    assert enriched["effective_download_mbps"] == 180.0
    assert enriched["effective_upload_mbps"] == 82.0
    assert enriched["bufferbloat_grade"] == "B"
    assert enriched["parallel_download_gain_ratio"] == 1.5
    assert set(_use_case_scores(enriched)) == {"balanced", "realtime", "streaming", "bulk", "upload_backup"}

    doc = {"route": {"final": "direct"}}
    latest = {
        "direct": sample(tag="direct", score=68.0, confidence=90.0, stability=86.0),
        "ext-fast": sample(tag="ext-fast", score=84.0, confidence=94.0, stability=92.0),
    }
    decision = _smart_route_decision(
        doc,
        latest,
        min_confidence=75.0,
        min_score_gain=6.0,
        minimum_candidate_score=55.0,
    )
    assert decision["candidate_tag"] == "ext-fast"
    assert decision["should_switch"] is True
    assert decision["reason"] == "candidate_clears_hysteresis"

    close_latest = {
        "direct": sample(tag="direct", score=80.0, confidence=92.0, stability=92.0),
        "ext-fast": sample(tag="ext-fast", score=82.0, confidence=94.0, stability=93.0),
    }
    hold = _smart_route_decision(
        doc,
        close_latest,
        min_confidence=75.0,
        min_score_gain=6.0,
        minimum_candidate_score=55.0,
    )
    assert hold["should_switch"] is False
    assert hold["reason"] == "hysteresis_hold"

    failed_latest = {
        "direct": sample(tag="direct", score=0.0, confidence=90.0, stability=20.0, ok=False),
        "ext-fast": sample(tag="ext-fast", score=76.0, confidence=90.0, stability=88.0),
    }
    failover = _smart_route_decision(
        doc,
        failed_latest,
        min_confidence=75.0,
        min_score_gain=6.0,
        minimum_candidate_score=55.0,
    )
    assert failover["should_switch"] is True
    assert failover["reason"] == "current_unhealthy_or_untrusted"

    baseline = _enrich_v4(sample(tag="ext-a", score=70.0))
    tuned_raw = sample(tag="ext-a", score=80.0)
    tuned_raw.update({"download_mbps": 145.0, "parallel_download_mbps": 210.0, "upload_mbps": 70.0, "parallel_upload_mbps": 95.0, "loaded_latency_ms": 43.0})
    tuned = _enrich_v4(tuned_raw)
    ab = _ab_decision(baseline, tuned, OptimizeIn())
    assert ab["keep_tuning"] is True
    assert ab["score_gain"] > 0

    apply_script = _tuning_apply_v4_script()
    rollback_script = _tuning_rollback_v4_script()
    assert "net.ipv4.tcp_congestion_control=bbr" in apply_script
    assert "net.core.default_qdisc=fq" in apply_script
    assert "net.ipv4.tcp_mtu_probing=1" in apply_script
    assert "tcp-accelerator-v4-backup.json" in apply_script
    assert "tcp_mtu_probing" in rollback_script
    assert "tc qdisc replace" not in apply_script
    assert "iptables" not in apply_script
    assert "nft" not in apply_script

    print("OUTBOUND_PERFORMANCE_V268_SMOKE_OK")


if __name__ == "__main__":
    main()
