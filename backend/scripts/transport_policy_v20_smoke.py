from __future__ import annotations

import math
from datetime import datetime

from app import transport_policy_v19 as v19
from app import transport_policy_v20 as v20


class Row:
    def __init__(
        self,
        transport: str,
        priority: int,
        row_id: int,
        *,
        enabled: bool = True,
        status: str = "online",
        latency_ms: int | None = None,
    ) -> None:
        self.transport = transport
        self.priority = priority
        self.id = row_id
        self.enabled = enabled
        self.status = status
        self.latency_ms = latency_ms
        self.last_healthy_at = datetime.utcnow()


def prime(
    tunnel_id: int,
    name: str,
    values: list[float],
) -> None:
    history = v19._history_for(
        tunnel_id,
        name,
    )
    history.clear()
    history.extend(values)


def main() -> None:
    tunnel_id = 50020

    v19._latency_history.clear()
    v20._legacy_health_cache.clear()
    v20._legacy_probe_cursor.clear()
    v20._last_legacy_challenger_probe.clear()

    rows = [
        Row("quic_2027", 30, 1),
        Row("tcp_2027", 40, 2),
        Row("kcp_2027", 10, 3),
        Row("backhaul", 100, 4),
        Row("ssh_tun", 200, 5),
    ]

    for name, values in {
        "quic_2027": [95, 96, 95, 95],
        "tcp_2027": [99, 100, 99, 100],
        "kcp_2027": [80, 80, 81, 80],
        "backhaul": [92, 92, 93, 92],
        "ssh_tun": [74, 75, 74, 75],
    }.items():
        prime(tunnel_id, name, values)

    health = {
        "quic_2027": {
            "ok": True,
            "latency_ms": 95,
            "packet_loss_pct": 0.0,
        },
        "tcp_2027": {
            "ok": True,
            "latency_ms": 99,
            "packet_loss_pct": 0.0,
        },
        "kcp_2027": {
            "ok": True,
            "latency_ms": 80,
            "packet_loss_pct": 100.0,
        },
        "backhaul": {
            "ok": True,
            "latency_ms": 92,
        },
        "ssh_tun": {
            "ok": True,
            "latency_ms": 74,
        },
    }

    best, scores = v20.choose_best_name_v20(
        tunnel_id,
        rows,
        health,
    )

    assert best == "ssh_tun", (best, scores)
    assert math.isinf(
        v20.performance_score(
            tunnel_id,
            "kcp_2027",
            health["kcp_2027"],
        )
    )

    ssh_score = v20.performance_score(
        tunnel_id,
        "ssh_tun",
        health["ssh_tun"],
    )
    raw_ssh_score = v19.quality_score(
        tunnel_id,
        "ssh_tun",
        health["ssh_tun"],
    )

    assert abs(
        ssh_score
        - raw_ssh_score
        - v20.UNKNOWN_LOSS_PENALTY
    ) < 0.001

    slower_legacy = dict(health)
    slower_legacy["ssh_tun"] = {
        "ok": True,
        "latency_ms": 96,
    }
    prime(
        tunnel_id,
        "ssh_tun",
        [96, 96, 97, 96],
    )

    best2, scores2 = v20.choose_best_name_v20(
        tunnel_id,
        rows,
        slower_legacy,
    )

    assert best2 == "quic_2027", (best2, scores2)

    v20._cache_put(
        tunnel_id,
        "backhaul",
        100.0,
        health["backhaul"],
    )

    assert v20._cache_get(
        tunnel_id,
        "backhaul",
        110.0,
        20.0,
    ) is not None

    assert v20._cache_get(
        tunnel_id,
        "backhaul",
        130.1,
        20.0,
    ) is None

    assert v20._materially_better(80.0, 100.0)
    assert not v20._materially_better(96.0, 100.0)

    print(
        "TRANSPORT_POLICY_V20_SMOKE_OK "
        "all_transports=1 "
        "loss_guard=1 "
        "legacy_uncertainty_penalty=1 "
        "cache_ttl=1 "
        "hysteresis=1"
    )


if __name__ == "__main__":
    main()
