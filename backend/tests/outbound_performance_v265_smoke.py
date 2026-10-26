from __future__ import annotations

from app.routers.outbound_performance_v265 import (
    _confidence_score,
    _enrich_result,
    _percentile,
    _profile_budget,
    _recommendations,
    _stability_score,
)


def sample(tag: str, *, score: float, latency: float, download: float, upload: float, jitter: float = 2.0, loss: float = 0.0):
    return {
        "ok": True,
        "advanced_ok": True,
        "tag": tag,
        "profile": "standard",
        "score": score,
        "score_version": 2,
        "latency_ms": latency,
        "jitter_ms": jitter,
        "probe_loss_pct": loss,
        "latency_samples_ms": [latency - 2, latency, latency + 2, latency + 4, latency + 1, latency - 1],
        "loaded_latency_samples_ms": [latency + 10, latency + 12, latency + 11, latency + 14, latency + 13],
        "loaded_jitter_ms": jitter + 1,
        "loaded_probe_loss_pct": loss,
        "bufferbloat_ms": 12.0,
        "download_mbps": download * 0.8,
        "upload_mbps": upload * 0.8,
        "parallel_download_mbps": download,
        "parallel_upload_mbps": upload,
        "download_bytes": 16_000_000,
        "upload_bytes": 6_000_000,
        "parallel_download_bytes": 10_000_000,
        "parallel_upload_bytes": 4_000_000,
    }


def main() -> None:
    assert _percentile([10, 20, 30, 40], 0.50) == 25.0
    assert _percentile([10, 20, 30, 40], 0.95) == 38.5
    assert _percentile([], 0.95) is None

    quick = _profile_budget("quick")
    standard = _profile_budget("standard")
    full = _profile_budget("full")
    assert quick["payload_total_upper_bound_bytes"] == 8_000_000
    assert standard["payload_total_upper_bound_bytes"] == 86_000_000
    assert full["payload_total_upper_bound_bytes"] == 217_000_000
    assert quick["estimated_wire_upper_bound_bytes"] > quick["payload_total_upper_bound_bytes"]

    stable = sample("ext-stable", score=88, latency=35, download=220, upload=90)
    unstable = sample("ext-unstable", score=88, latency=35, download=220, upload=90, jitter=30, loss=12)
    assert _stability_score(stable) > _stability_score(unstable)
    assert _confidence_score(stable, "standard") >= 95

    enriched = _enrich_result(stable)
    assert enriched["score_version"] == 3
    assert enriched["latency_p50_ms"] is not None
    assert enriched["latency_p95_ms"] >= enriched["latency_p50_ms"]
    assert enriched["loaded_latency_p95_ms"] >= enriched["loaded_latency_p50_ms"]
    assert enriched["confidence_level"] == "high"
    assert enriched["transfer"]["measured_payload_bytes"] == 36_000_000
    assert enriched["transfer"]["payload_total_upper_bound_bytes"] == 86_000_000
    assert enriched["transfer"]["loaded_phase_is_bounded_but_not_byte_metered"] is True

    latest = {
        "ext-fast": sample("ext-fast", score=90, latency=45, download=500, upload=100),
        "ext-low-latency": sample("ext-low-latency", score=86, latency=18, download=180, upload=80),
        "ext-upload": sample("ext-upload", score=84, latency=30, download=160, upload=240),
        "ext-stable": sample("ext-stable", score=89, latency=25, download=200, upload=100, jitter=0.5),
    }
    recommendations = _recommendations(latest)
    assert recommendations["best_download"]["tag"] == "ext-fast"
    assert recommendations["best_upload"]["tag"] == "ext-upload"
    assert recommendations["lowest_latency"]["tag"] == "ext-low-latency"
    assert recommendations["most_stable"]["tag"] == "ext-stable"
    assert recommendations["best_overall"] is not None

    failed = _enrich_result({"ok": False, "tag": "ext-dead", "profile": "quick", "score": 99})
    assert failed["score"] == 0.0
    assert failed["quality"] == "failed"

    print("outbound performance v265 smoke: ok")


if __name__ == "__main__":
    main()
