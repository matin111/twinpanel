from __future__ import annotations

from app.routers.outbound_performance_v261 import (
    MAX_HISTORY_PER_TAG,
    PERFORMANCE_SCHEMA,
    _benchmark_script,
    _clean_state,
    score_benchmark,
)


def main() -> None:
    script = _benchmark_script("ext-smoke", "standard")
    compile(script, "<outbound-performance-script>", "exec")

    required_tokens = (
        "twinpanel-outbound-performance",
        "speed.cloudflare.com/__down",
        "speed.cloudflare.com/__up",
        "--socks5-hostname",
        '"route": {"final": TAG}',
        '"probe_loss_pct"',
        '"download_mbps"',
        '"upload_mbps"',
    )
    for token in required_tokens:
        assert token in script, token

    excellent = score_benchmark(
        {
            "ok": True,
            "latency_ms": 24.0,
            "jitter_ms": 1.2,
            "probe_loss_pct": 0.0,
            "download_mbps": 420.0,
            "upload_mbps": 160.0,
        },
        "balanced",
    )
    degraded = score_benchmark(
        {
            "ok": True,
            "latency_ms": 180.0,
            "jitter_ms": 28.0,
            "probe_loss_pct": 35.0,
            "download_mbps": 8.0,
            "upload_mbps": 2.0,
        },
        "balanced",
    )
    failed = score_benchmark({"ok": False}, "download")

    assert 0.0 <= float(degraded["score"]) < float(excellent["score"]) <= 100.0
    assert excellent["quality"] in {"excellent", "good"}
    assert failed == {"score": 0.0, "quality": "failed", "score_profile": "download"}

    raw_history = [{"tag": "ext-smoke", "score": float(index)} for index in range(MAX_HISTORY_PER_TAG + 5)]
    state = _clean_state(
        {
            "schema": 99,
            "updated_at": "now",
            "latest": {"ext-smoke": raw_history[-1], "bad": "not-a-dict"},
            "history": {"ext-smoke": raw_history, "bad": "not-a-list"},
        }
    )
    assert state["schema"] == PERFORMANCE_SCHEMA
    assert list(state["latest"]) == ["ext-smoke"]
    assert len(state["history"]["ext-smoke"]) == MAX_HISTORY_PER_TAG
    assert state["history"]["ext-smoke"][0]["score"] == 5.0

    print("outbound performance v261 smoke: ok")


if __name__ == "__main__":
    main()
