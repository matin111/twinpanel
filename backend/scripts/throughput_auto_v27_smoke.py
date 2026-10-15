from __future__ import annotations

import json
from types import SimpleNamespace

from app.throughput_auto_v27 import (
    THROUGHPUT_SAMPLE_TTL_SECONDS,
    _adjust_ranked_for_throughput,
    _benchmark_meta,
    throughput_penalty,
)


def row(name: str, sample: dict | None = None):
    cfg = {
        "interface": "tp-test0",
        "iran_ip": "10.200.0.1",
        "exit_ip": "10.200.0.2",
    }
    if sample is not None:
        cfg["auto_throughput"] = sample
    return SimpleNamespace(
        transport=name,
        config_text=json.dumps(cfg),
    )


def sample(now: float, down: float, up: float, *, age: float = 0.0):
    return {
        "version": 27,
        "measured_at_epoch": now - age,
        "download_mbps": down,
        "upload_mbps": up,
        "effective_mbps": min(down, up),
    }


def main() -> None:
    now = 2_000_000_000.0

    base = [
        ("slow", 80.0),
        ("fast", 90.0),
        ("unknown", 85.0),
    ]

    rows = [
        row("slow", sample(now, 1.0, 12.0)),
        row("fast", sample(now, 25.0, 22.0)),
        row("unknown", None),
    ]

    adjusted = _adjust_ranked_for_throughput(
        base,
        rows,
        now_epoch=now,
    )

    assert adjusted[0][0] == "fast", adjusted
    scores = dict(adjusted)
    assert scores["slow"] > scores["unknown"] > scores["fast"], scores

    # One isolated sample must not change historical V20 ranking.
    one_sample = _adjust_ranked_for_throughput(
        base,
        [
            row("slow", sample(now, 1.0, 12.0)),
            row("fast", None),
            row("unknown", None),
        ],
        now_epoch=now,
    )
    assert one_sample == base, one_sample

    # Expired samples must not activate throughput scoring.
    expired_age = THROUGHPUT_SAMPLE_TTL_SECONDS + 1.0
    expired = _adjust_ranked_for_throughput(
        base,
        [
            row("slow", sample(now, 1.0, 12.0, age=expired_age)),
            row("fast", sample(now, 25.0, 22.0, age=expired_age)),
            row("unknown", None),
        ],
        now_epoch=now,
    )
    assert expired == base, expired

    assert throughput_penalty(1.0) > throughput_penalty(10.0)
    assert throughput_penalty(20.0) == 0.0
    assert throughput_penalty(200.0) == 0.0

    meta = _benchmark_meta(rows[0], 5)
    assert meta is not None
    assert meta["interface"] == "tp-test0"
    assert meta["iran_ip"] == "10.200.0.1"
    assert meta["exit_ip"] == "10.200.0.2"

    print(
        "THROUGHPUT_AUTO_V27_SMOKE_OK "
        f"fast_score={scores['fast']:.2f} "
        f"unknown_score={scores['unknown']:.2f} "
        f"slow_score={scores['slow']:.2f}"
    )


if __name__ == "__main__":
    main()
