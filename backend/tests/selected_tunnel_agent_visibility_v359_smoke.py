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


def test_stale_report_grace_preserves_only_last_verified_route() -> None:
    source = TUNNELS.read_text(encoding="utf-8")
    election = source.split("def _select_service_route_tunnel_ids(", 1)[1]
    assert_true(
        "TWINPANEL_IRAN_ROUTE_STALE_REPORT_GRACE_V2" in election,
        "busy Iran Agent reports must use bounded physical health grace",
    )
    assert_true(
        "active_member.last_healthy_at" in election
        and "0 <= age <= 300" in election,
        "route grace must require a recent confirmed physical carrier",
    )
    assert_true(
        "current_id is None" in election
        and "_service_route_selected[key] = int(candidate.id)" in election,
        "restart with empty election cache must recover proven physical transport",
    )
    assert_true(
        "active_member.status or" in election
        and "fresh_hard_failure" in election,
        "new selection must be online and explicit fresh errors fail closed",
    )
    assert_true(
        "selected_ids.add(int(candidate.id))" in election,
        "stale telemetry must not drop verified selected service route",
    )


if __name__ == "__main__":
    test_selected_tunnel_becomes_agent_visible_only_after_install()
    test_desired_contract_requires_active_tunnel()
    test_service_route_requires_online_status()
    test_stale_report_grace_preserves_only_last_verified_route()
    print("SELECTED_TUNNEL_AGENT_VISIBILITY_V359=PASS")
