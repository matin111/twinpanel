from __future__ import annotations

import time

from . import throughput_auto_v27 as v27


# ============================================================
# TWINPANEL THROUGHPUT UNKNOWN NEUTRALITY V30
#
# V27 gives candidates without a fresh throughput sample a fixed penalty of
# 20. Production audit showed measured candidates on a slow/asymmetric path
# commonly carry throughput penalties around 37-39. When one candidate's sample
# expires, that fixed 20 can therefore become an artificial ~18-point bonus.
#
# V30 changes only the unknown-sample penalty used while throughput scoring is
# active. Unknown candidates inherit at least the worst penalty among currently
# fresh measured candidates (and never less than V27's original floor). This
# makes missing/expired data neutral rather than advantageous while preserving:
#   * V27 benchmark schedule, TTL, byte/time caps and persistence
#   * V20 latency/loss/stability score and anti-flap behavior
#   * V29 runtime benchmark metadata
#   * Manual authority, routes, firewall, services and database schema
# ============================================================


def unknown_penalty_floor_v30(
    samples_by_name: dict[str, dict | None],
) -> float:
    penalties = [
        float(v27.throughput_penalty(sample["effective_mbps"]))
        for sample in samples_by_name.values()
        if sample is not None
    ]

    if not penalties:
        return float(v27.UNKNOWN_THROUGHPUT_PENALTY)

    return max(
        float(v27.UNKNOWN_THROUGHPUT_PENALTY),
        max(penalties),
    )


def adjust_ranked_for_throughput_v30(
    ranked: list[tuple[str, float]],
    rows: list,
    *,
    now_epoch: float | None = None,
) -> list[tuple[str, float]]:
    if not ranked:
        return []

    now = time.time() if now_epoch is None else float(now_epoch)

    row_by_name = {
        v27._name(getattr(row, "transport", "")): row
        for row in rows
    }

    samples = {
        name: v27._sample(row_by_name[name], now)
        for name, _score in ranked
        if name in row_by_name
    }

    fresh_count = sum(
        1
        for sample in samples.values()
        if sample is not None
    )

    # Preserve V27's safety gate exactly: one isolated throughput result must
    # never distort the candidate set.
    if fresh_count < v27.MIN_FRESH_SAMPLES_FOR_SCORING:
        return list(ranked)

    unknown_penalty = unknown_penalty_floor_v30(samples)

    adjusted: list[tuple[str, float, int]] = []

    for index, (name, base_score) in enumerate(ranked):
        sample = samples.get(name)

        if sample is None:
            penalty = unknown_penalty
        else:
            penalty = v27.throughput_penalty(
                sample["effective_mbps"]
            )

        adjusted.append(
            (
                name,
                float(base_score) + float(penalty),
                index,
            )
        )

    adjusted.sort(
        key=lambda item: (
            item[1],
            item[2],
            item[0],
        )
    )

    return [
        (name, score)
        for name, score, _index in adjusted
    ]


def install_throughput_unknown_neutral_v30() -> None:
    # ranked_all_v27 resolves this helper from throughput_auto_v27 module
    # globals at call time, so replacing only the helper changes neither V20
    # selection flow nor V27 benchmark scheduling/persistence.
    v27._adjust_ranked_for_throughput = (
        adjust_ranked_for_throughput_v30
    )

    print(
        "TWINPANEL_THROUGHPUT_UNKNOWN_NEUTRAL_V30_ACTIVE "
        "unknown_floor=worst_fresh_penalty "
        "base_floor=20 scoring_weights_unchanged=1 "
        "benchmark_schedule_unchanged=1 routes_unchanged=1",
        flush=True,
    )
