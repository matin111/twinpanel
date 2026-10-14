#!/usr/bin/env python3
from __future__ import annotations

import math
from types import SimpleNamespace

from app import transport_policy_v19 as policy


def row(row_id: int, name: str, priority: int):
    return SimpleNamespace(
        id=row_id,
        transport=name,
        priority=priority,
        enabled=True,
    )


def reset_state() -> None:
    policy._latency_history.clear()
    policy._candidate_name.clear()
    policy._candidate_since.clear()


def main() -> None:
    reset_state()

    tunnel_id = 5
    rows = [
        row(1, "kcp_2027", 10),
        row(2, "arq_2027", 20),
        row(3, "quic_2027", 30),
        row(4, "tcp_2027", 40),
        row(5, "backhaul", 100),
    ]

    # Reproduce the important production shape: KCP is unusable; ARQ may have
    # a low nominal RTT but spike badly; QUIC stays stable; TCP is close behind.
    for value in (90, 91, 350, 89, 90):
        policy._history_for(tunnel_id, "arq_2027").append(float(value))

    for value in (90, 91, 89, 90, 90):
        policy._history_for(tunnel_id, "quic_2027").append(float(value))

    for value in (91, 92, 90, 91, 92):
        policy._history_for(tunnel_id, "tcp_2027").append(float(value))

    health = {
        "kcp_2027": {
            "ok": True,
            "latency_ms": 80,
            "packet_loss_pct": 100.0,
        },
        "arq_2027": {
            "ok": True,
            "latency_ms": 90,
            "packet_loss_pct": 0.0,
        },
        "quic_2027": {
            "ok": True,
            "latency_ms": 90,
            "packet_loss_pct": 0.0,
        },
        "tcp_2027": {
            "ok": True,
            "latency_ms": 91,
            "packet_loss_pct": 0.0,
        },
        "backhaul": {
            "ok": True,
            "latency_ms": 93,
        },
    }

    kcp_score = policy.quality_score(
        tunnel_id,
        "kcp_2027",
        health["kcp_2027"],
    )
    assert math.isinf(kcp_score), "100% loss KCP must never be selected"

    best, scores = policy.choose_best_name_v19(
        tunnel_id,
        rows,
        health,
    )

    assert best == "quic_2027", (
        "stable QUIC should beat spike-heavy ARQ and slightly slower TCP; "
        f"got {best!r} scores={scores!r}"
    )

    assert scores["quic_2027"] < scores["arq_2027"]
    assert scores["quic_2027"] < scores["tcp_2027"]

    # No healthy modern path -> retain a healthy legacy fallback.
    fallback_health = {
        "kcp_2027": {"ok": False, "latency_ms": None},
        "arq_2027": {"ok": False, "latency_ms": None},
        "quic_2027": {"ok": False, "latency_ms": None},
        "tcp_2027": {"ok": False, "latency_ms": None},
        "backhaul": {"ok": True, "latency_ms": 95},
    }

    fallback, _ = policy.choose_best_name_v19(
        tunnel_id,
        rows,
        fallback_health,
    )
    assert fallback == "backhaul"

    assert policy._materially_better(90.0, 110.0) is True
    assert policy._materially_better(100.0, 104.0) is False

    # Candidate hold state must not instantly report stable.
    assert policy._candidate_stable(tunnel_id, "quic_2027", 100.0) == 0.0
    assert policy._candidate_stable(tunnel_id, "quic_2027", 129.0) == 29.0
    assert policy._candidate_stable(tunnel_id, "quic_2027", 131.0) == 31.0

    print("TWINPANEL_TRANSPORT_POLICY_V19_SMOKE_OK")
    print(f"BEST={best}")
    print(
        "SCORES="
        + ",".join(
            f"{name}:{score:.2f}"
            for name, score in sorted(scores.items(), key=lambda item: item[1])
        )
    )
    print("LOSS_REJECTION=OK")
    print("LEGACY_FALLBACK=OK")
    print("HYSTERESIS=OK")


if __name__ == "__main__":
    main()
