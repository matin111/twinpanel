from __future__ import annotations

import json
from types import SimpleNamespace

from app import throughput_auto_v27 as v27
from app.throughput_unknown_neutral_v30 import (
    adjust_ranked_for_throughput_v30,
    install_throughput_unknown_neutral_v30,
    unknown_penalty_floor_v30,
)


NOW = 1_000_000.0


def row(name: str, effective: float | None):
    cfg = {}

    if effective is not None:
        cfg["auto_throughput"] = {
            "version": 27,
            "measured_at_epoch": NOW - 10.0,
            "download_mbps": effective,
            "upload_mbps": effective,
            "effective_mbps": effective,
            "max_bytes_per_direction": int(v27.BENCHMARK_MAX_BYTES),
            "max_seconds_per_direction": float(v27.BENCHMARK_SECONDS),
            "source": "smoke",
        }

    return SimpleNamespace(
        transport=name,
        config_text=json.dumps(cfg),
    )


def main() -> None:
    fast = row("fast", 20.0)
    slow = row("slow", 1.0)
    unknown = row("unknown", None)

    rows = [fast, slow, unknown]

    samples = {
        item.transport: v27._sample(item, NOW)
        for item in rows
    }

    floor = unknown_penalty_floor_v30(samples)
    slow_penalty = v27.throughput_penalty(1.0)

    assert abs(floor - slow_penalty) < 1e-9
    assert floor > v27.UNKNOWN_THROUGHPUT_PENALTY

    ranked = [
        ("fast", 100.0),
        ("slow", 100.0),
        ("unknown", 100.0),
    ]

    adjusted = adjust_ranked_for_throughput_v30(
        ranked,
        rows,
        now_epoch=NOW,
    )

    scores = dict(adjusted)

    assert abs(scores["fast"] - 100.0) < 1e-9
    assert abs(scores["slow"] - (100.0 + slow_penalty)) < 1e-9
    assert abs(scores["unknown"] - (100.0 + floor)) < 1e-9
    assert scores["unknown"] >= scores["slow"]

    # Preserve V27's minimum-two-fresh-samples safety gate.
    one_measured_rows = [
        row("fast", 20.0),
        row("unknown", None),
    ]
    one_ranked = [
        ("fast", 50.0),
        ("unknown", 40.0),
    ]

    assert adjust_ranked_for_throughput_v30(
        one_ranked,
        one_measured_rows,
        now_epoch=NOW,
    ) == one_ranked

    install_throughput_unknown_neutral_v30()

    assert (
        v27._adjust_ranked_for_throughput
        is adjust_ranked_for_throughput_v30
    )

    print(
        "THROUGHPUT_UNKNOWN_NEUTRAL_V30_SMOKE_OK "
        f"base_unknown={v27.UNKNOWN_THROUGHPUT_PENALTY:.1f} "
        f"derived_unknown={floor:.1f} "
        "expired_sample_bonus_removed=1 "
        "min_sample_gate_preserved=1 runtime_hook=1"
    )


if __name__ == "__main__":
    main()
