from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SELECTED = ROOT / "backend/app/routers/tunnel_selected_v358.py"
TUNNELS = ROOT / "backend/app/routers/tunnels.py"


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_selected_tunnel_becomes_agent_visible_only_after_install() -> None:
    source = SELECTED.read_text(encoding="utf-8")

    create_index = source.index("is_active=False")
    install_index = source.index("install_result = await install_modern_transport")
    visibility_index = source.index("pending.is_active = True")
    select_index = source.index("selection_result = await select_modern_transport_manual")

    assert_true(
        create_index < install_index < visibility_index < select_index,
        "selected pair must start inactive, install first, then become Agent-visible before cutover acceptance",
    )
    assert_true(
        "pending.status = TunnelStatus.ONLINE" not in source,
        "Agent visibility step must not promote the new pair to ONLINE",
    )
    assert_true(
        "pending.active_transport =" not in source,
        "Agent visibility step must not bypass manual transport authority",
    )


def test_desired_contract_requires_active_tunnel() -> None:
    source = TUNNELS.read_text(encoding="utf-8")
    route_index = source.index('@router.get("/node/{node_id}/desired")')
    desired = source[route_index: route_index + 1800]
    assert_true(
        "Tunnel.is_active.is_(True)" in desired,
        "Agent desired feed must remain explicitly gated by is_active",
    )


def test_service_route_requires_online_status() -> None:
    source = TUNNELS.read_text(encoding="utf-8")
    function_index = source.index("def _service_route_member_usable")
    body = source[function_index: function_index + 700]
    assert_true("tunnel.is_active" in body, "service route must require active tunnel")
    assert_true(
        "tunnel.status == TunnelStatus.ONLINE" in body,
        "service route must also require ONLINE status",
    )


if __name__ == "__main__":
    test_selected_tunnel_becomes_agent_visible_only_after_install()
    test_desired_contract_requires_active_tunnel()
    test_service_route_requires_online_status()
    print("SELECTED_TUNNEL_AGENT_VISIBILITY_V359=PASS")
