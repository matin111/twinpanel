from __future__ import annotations

from types import SimpleNamespace

from app.transport_policy_v16 import (
    MANAGED_TRANSPORT_NAMES,
    apply_overlay_loss_policy,
    choose_best_name,
    policy_priority,
)


def row(name: str, row_id: int = 1):
    return SimpleNamespace(
        transport=name,
        priority=999,
        id=row_id,
    )


def main() -> None:
    rows = [
        row("quic_2027", 1),
        row("kcp_2027", 2),
        row("mtunnel", 3),
        row("backhaul", 4),
        row("ssh_tun", 5),
    ]

    # A healthy direct Backhaul carrier must beat every dependent overlay.
    health = {
        "backhaul": {"ok": True},
        "mtunnel": {"ok": True},
        "kcp_2027": {"ok": True},
        "quic_2027": {"ok": True},
        "ssh_tun": {"ok": True},
    }
    assert choose_best_name(rows, health) == "backhaul"

    # If Backhaul fails, another independent direct path wins before overlays.
    health["backhaul"] = {"ok": False}
    assert choose_best_name(rows, health) == "mtunnel"

    # If every direct path fails, KCP is the preferred measured overlay fallback.
    health["mtunnel"] = {"ok": False}
    health["ssh_tun"] = {"ok": False}
    assert choose_best_name(rows, health) == "kcp_2027"

    # A reachability PASS with severe loss must not qualify for auto selection.
    degraded = apply_overlay_loss_policy(
        {
            "ok": True,
            "latency_ms": 83,
            "packet_loss_pct": 15.0,
            "error": None,
        }
    )
    assert degraded["ok"] is False
    assert "high_packet_loss" in str(degraded["error"])

    clean = apply_overlay_loss_policy(
        {
            "ok": True,
            "latency_ms": 83,
            "packet_loss_pct": 0.0,
            "error": None,
        }
    )
    assert clean["ok"] is True

    # The autonomous repair scope must include direct-only partial tunnels.
    for name in (
        "backhaul",
        "mtunnel",
        "ssh_tun",
        "kcp_2027",
        "arq_2027",
        "quic_2027",
        "tcp_2027",
        "ssh_relay",
    ):
        assert name in MANAGED_TRANSPORT_NAMES

    assert policy_priority("backhaul") < policy_priority("mtunnel")
    assert policy_priority("mtunnel") < policy_priority("kcp_2027")

    print("TRANSPORT_POLICY_V16_SMOKE_OK")


if __name__ == "__main__":
    main()
