from __future__ import annotations

from types import SimpleNamespace

from app import managed_ops, tp2027_provision
from app.backhaul_multi_exit_v16 import (
    backhaul_forward_port,
    install_backhaul_peer_v16,
)
from app.manager_runtime_v16 import install_manager_runtime_v16
from app.routers import tunnel_managed, tunnels
from app.tp2027_multi_exit_v18 import (
    _public_firewall_script,
    _public_service_unit,
    install_tp2027_overlays_v18,
)
from app.transport_policy_v17 import (
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
        row("arq_2027", 3),
        row("backhaul", 4),
        row("mtunnel", 5),
        row("ssh_tun", 6),
    ]

    health = {
        "backhaul": {"ok": True},
        "mtunnel": {"ok": True},
        "ssh_tun": {"ok": True},
        "kcp_2027": {"ok": True},
        "arq_2027": {"ok": True},
        "quic_2027": {"ok": True},
    }
    assert choose_best_name(rows, health) == "kcp_2027"

    health["kcp_2027"] = {"ok": False}
    assert choose_best_name(rows, health) == "arq_2027"

    health["arq_2027"] = {"ok": False}
    health["quic_2027"] = {"ok": False}
    assert choose_best_name(rows, health) == "backhaul"

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

    assert policy_priority("kcp_2027") < policy_priority("arq_2027")
    assert policy_priority("arq_2027") < policy_priority("quic_2027")
    assert policy_priority("quic_2027") < policy_priority("backhaul")

    # Explicit legacy Backhaul still has collision-free mappings.
    port_a = backhaul_forward_port(9005)
    port_b = backhaul_forward_port(9009)
    assert port_a != port_b

    # Public-direct service units must not depend on the Backhaul carrier.
    unit = _public_service_unit(
        "kcp_2027",
        9,
        role="iran",
        exit_public_ip="198.51.100.20",
    )
    assert "--peer 198.51.100.20:45109" in unit
    assert "twinpanel-backhaul-9.service" not in unit

    firewall = _public_firewall_script(9, "192.0.2.10")
    assert "192.0.2.10/32" in firewall
    assert "TP2027_PUBLIC_IN" in firewall
    assert "bh9" not in firewall

    install_manager_runtime_v16()
    assert tunnels._install_backhaul_peer is install_backhaul_peer_v16

    # New managed tunnels do not auto-create MTunnel/Backhaul/SSH TUN.
    assert tuple(tunnel_managed._TRANSPORTS) == ()
    assert tuple(tunnel_managed._SELECTION_ORDER[:4]) == (
        "kcp_2027",
        "arq_2027",
        "quic_2027",
        "tcp_2027",
    )
    assert tuple(managed_ops.DIRECT_BASE_ORDER) == ()
    assert tuple(managed_ops.EXPECTED_ORDER[:4]) == (
        "kcp_2027",
        "arq_2027",
        "quic_2027",
        "tcp_2027",
    )
    assert tunnel_managed.install_tp2027_overlays is install_tp2027_overlays_v18
    assert managed_ops.install_tp2027_overlays is install_tp2027_overlays_v18
    assert tuple(tp2027_provision.TP2027_PRIORITY) == (
        "kcp_2027",
        "arq_2027",
        "quic_2027",
        "tcp_2027",
    )

    print("TRANSPORT_POLICY_V18_MULTI_EXIT_SMOKE_OK")


if __name__ == "__main__":
    main()
