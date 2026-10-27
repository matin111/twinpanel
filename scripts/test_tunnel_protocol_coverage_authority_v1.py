from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, needle: str, message: str) -> None:
    if needle not in text:
        raise AssertionError(message)


def main() -> None:
    component = read("components/smart-transports-runtime-v26.tsx")
    api_client = read("lib/modern-transport-api.ts")
    binding = read("backend/app/modern_protocol_tunnel_binding_v251.py")
    inventory_router = read("backend/app/routers/modern_protocol_admin_v3.py")

    # The transport UI must read the existing backend inventory instead of
    # treating the historical five-protocol list as the full service plane.
    require(
        api_client,
        "/v1/settings/vpn/modern-protocols",
        "modern protocol inventory endpoint is not wired into the transport UI client",
    )
    require(
        api_client,
        "protocolInventory:",
        "modernTransportApi.protocolInventory is missing",
    )

    require(
        component,
        "const classicProtocols",
        "classic protocol baseline is missing",
    )
    require(
        component,
        "selectedTunnel?.exit_node_id",
        "protocol inventory is not scoped to the selected tunnel Exit node",
    )
    require(
        component,
        'normalized(item.status)==="not_installed"',
        "not-installed modern protocols are not filtered from coverage",
    )
    require(
        component,
        "protocolInventoryError",
        "modern inventory fail-soft state is missing",
    )

    render_count = len(re.findall(r"protocolCoverage\.map\s*\(", component))
    if render_count < 2:
        raise AssertionError(
            "protocolCoverage must render in both the service-plane matrix and transport cards"
        )

    if re.search(r"\bprotocols\.map\s*\(", component):
        raise AssertionError(
            "legacy hard-coded protocols.map rendering returned to the transport UI"
        )

    # Backend authority: V251 must remain the route/binding source for all
    # modern protocols. The UI inventory is informational; it never replaces
    # service-plane routing authority.
    require(
        binding,
        "MODERN_TUNNEL_PROTOCOLS",
        "V251 modern tunnel protocol registry is missing",
    )
    require(
        binding,
        "_modern_routes_for_exit",
        "V251 modern service-route builder is missing",
    )
    require(
        binding,
        "_service_routes_for_exit_v251",
        "V251 service-route wrapper is missing",
    )

    for protocol in (
        "hysteria2",
        "tuic",
        "anytls",
        "naive",
        "shadowtls",
        "snell",
        "mieru",
        "trusttunnel",
        "amneziawg",
        "sudoku",
    ):
        require(
            binding,
            f'"{protocol}"',
            f"modern tunnel binding lost protocol: {protocol}",
        )

    require(
        inventory_router,
        '"/modern-protocols"',
        "modern protocol inventory route is missing",
    )
    require(
        inventory_router,
        '"protocols": [',
        "modern protocol inventory no longer publishes per-node protocols",
    )

    print("TUNNEL_PROTOCOL_COVERAGE_AUTHORITY_V1=PASS")


if __name__ == "__main__":
    main()
