from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
BINDING = BACKEND / "app" / "active_l3_route_binding_v94.py"
REGISTRY = BACKEND / "app" / "unified_l3_candidate_registry_v79.py"
CANDIDATES = BACKEND / "app" / "transport_candidates" / "__init__.py"


def main() -> None:
    binding = BINDING.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")
    candidates = CANDIDATES.read_text(encoding="utf-8")

    required_binding = (
        "TWINPANEL_ACTIVE_L3_ROUTE_BINDING_V94",
        "active_transport",
        "candidate_runtime(name, int(tunnel.id))",
        'str(rt["network"])',
        'str(rt["iran_addr"])',
        'str(rt["exit_addr"])',
        'str(rt["interface"])',
        "tunnels._tunnel_addresses = _active_tunnel_addresses_v94",
        "tunnels._health_interface_name = _active_health_interface_v94",
        "tunnels._data_interface_name = _active_data_interface_v94",
        "authority=active_transport",
    )
    for token in required_binding:
        assert token in binding, token

    assert "apply_active_l3_route_binding_v94" in registry
    assert registry.index("apply_active_l3_route_binding_v94()") < registry.index(
        "source = core._AGENT_RECONCILE_V49"
    )

    # V202 factors candidate addressing through _l3_runtime while preserving
    # V94's authoritative contract: runtime() still returns the interface,
    # network and peer /30 addresses consumed by active_l3_route_binding_v94.
    for token in (
        '"interface": f"{interface_prefix}{tid}"[:15]',
        '"network": f"10.{octet}.{third}.{fourth}/30"',
        '"iran_addr": f"{iran_ip}/30"',
        '"exit_addr": f"{exit_ip}/30"',
        'transport="tp27_fast"',
        'octet=253',
        'interface_prefix="tp27"',
        'transport="spoof_wg"',
        'octet=250',
        'interface_prefix="tpsp"',
    ):
        assert token in candidates, token

    # Fast remains the established production runtime; Spoof WG is additive and
    # receives a disjoint /30/interface so active_transport authority can bind
    # either candidate without rewriting the V94 route-selection layer.
    assert "table = 29000 + (int(tunnel_id) % 900)" in candidates
    assert "table = 33000 + (int(tunnel_id) % 900)" in candidates

    print("ACTIVE_L3_ROUTE_BINDING_V94_V202_OK")


if __name__ == "__main__":
    main()
