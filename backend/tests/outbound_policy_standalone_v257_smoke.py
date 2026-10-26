from __future__ import annotations

from app.outbound_policy_standalone_adapters_v257 import (
    AMNEZIAWG_POLICY,
    STANDALONE_POLICY_SPECS,
    STANDALONE_RECONCILE_SCRIPT,
)
from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.routers.outbound_policy_center_v3 import (
    KERNEL_POLICY_SPECS,
    KERNEL_TUN_NAME,
    KERNEL_TUN_TAG,
    POLICY_SCHEMA,
    _PROTOCOLS,
    _PROTOCOL_BY_KEY,
    _apply_state_to_document,
    _clean_state,
    _effective_outbound,
    _generated_rule,
    _kernel_reconcile_script,
    _protocol_payload,
)

TARGETS = {"mieru", "trusttunnel", "amneziawg", "sudoku"}


def base_doc() -> dict:
    return {
        "inbounds": [],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {"type": "socks", "tag": "warp"},
        ],
        "route": {
            "final": "direct",
            "rules": [{"protocol": "dns", "action": "hijack-dns"}],
        },
    }


def state_with(**modes: str) -> dict:
    return _clean_state(
        {
            "policies": {
                key: {
                    "mode": mode,
                    "outbound_tag": "warp" if mode == "outbound" else None,
                }
                for key, mode in modes.items()
            }
        }
    )


def test_inventory_is_fifteen_of_fifteen_route_ready() -> None:
    keys = [str(item["key"]) for item in _PROTOCOLS]
    assert len(keys) == 15
    assert len(set(keys)) == 15
    assert set(keys) == set(ALL_PROTOCOL_KEYS)
    assert all(bool(item.get("policy_supported")) for item in _PROTOCOLS)
    assert all(item.get("reason") is None for item in _PROTOCOLS)
    assert POLICY_SCHEMA == 3

    assert _PROTOCOL_BY_KEY["mieru"]["adapter_kind"] == "standalone-socks"
    assert _PROTOCOL_BY_KEY["trusttunnel"]["adapter_kind"] == "standalone-socks"
    assert _PROTOCOL_BY_KEY["sudoku"]["adapter_kind"] == "standalone-tproxy"
    assert _PROTOCOL_BY_KEY["amneziawg"]["adapter_kind"] == "kernel-tun"
    assert _PROTOCOL_BY_KEY["amneziawg"]["source_cidr"] == "10.254.0.0/16"


def test_standalone_rules_are_real_singbox_matches() -> None:
    assert _generated_rule(
        "mieru", {"mode": "outbound", "outbound_tag": "warp"}
    ) == {
        "inbound": ["twinpanel-mieru-policy-in"],
        "action": "route",
        "outbound": "warp",
    }
    assert _generated_rule("trusttunnel", {"mode": "block"}) == {
        "inbound": ["twinpanel-trusttunnel-policy-in"],
        "action": "reject",
        "method": "default",
    }
    assert _generated_rule("sudoku", {"mode": "direct"}) == {
        "inbound": ["twinpanel-sudoku-policy-in"],
        "action": "route",
        "outbound": "direct",
    }
    assert _generated_rule(
        "amneziawg", {"mode": "outbound", "outbound_tag": "warp"}
    ) == {
        "source_ip_cidr": ["10.254.0.0/16"],
        "action": "route",
        "outbound": "warp",
    }


def test_reconcile_builds_all_standalone_policy_inbounds() -> None:
    state = state_with(
        mieru="outbound",
        trusttunnel="block",
        amneziawg="outbound",
        sudoku="direct",
    )
    doc, next_state = _apply_state_to_document(base_doc(), state, [])
    by_tag = {
        str(item.get("tag")): item
        for item in doc["inbounds"]
        if isinstance(item, dict) and item.get("tag")
    }

    assert by_tag["twinpanel-mieru-policy-in"] == {
        "type": "socks",
        "tag": "twinpanel-mieru-policy-in",
        "listen": "127.0.0.1",
        "listen_port": 19083,
    }
    assert by_tag["twinpanel-trusttunnel-policy-in"]["listen_port"] == 19084
    assert by_tag["twinpanel-sudoku-policy-in"]["type"] == "tproxy"
    assert by_tag["twinpanel-sudoku-policy-in"]["listen_port"] == 19085
    assert by_tag[KERNEL_TUN_TAG]["type"] == "tun"
    assert by_tag[KERNEL_TUN_TAG]["interface_name"] == KERNEL_TUN_NAME

    rules = next_state["generated_rules"]
    assert any(rule.get("inbound") == ["twinpanel-mieru-policy-in"] for rule in rules)
    assert any(rule.get("inbound") == ["twinpanel-trusttunnel-policy-in"] for rule in rules)
    assert any(rule.get("inbound") == ["twinpanel-sudoku-policy-in"] for rule in rules)
    assert any(rule.get("source_ip_cidr") == ["10.254.0.0/16"] for rule in rules)


def test_inherit_removes_standalone_managed_inbounds() -> None:
    active = state_with(mieru="direct", trusttunnel="direct", sudoku="direct")
    doc, active_state = _apply_state_to_document(base_doc(), active, [])
    inherited = _clean_state(active_state)
    for key in ("mieru", "trusttunnel", "sudoku"):
        inherited["policies"][key] = {"mode": "inherit", "outbound_tag": None}
    restored, restored_state = _apply_state_to_document(
        doc,
        inherited,
        list(active_state["generated_rules"]),
    )
    tags = {
        str(item.get("tag"))
        for item in restored["inbounds"]
        if isinstance(item, dict) and item.get("tag")
    }
    assert "twinpanel-mieru-policy-in" not in tags
    assert "twinpanel-trusttunnel-policy-in" not in tags
    assert "twinpanel-sudoku-policy-in" not in tags
    assert restored_state["generated_rules"] == []
    assert restored["route"]["rules"] == [{"protocol": "dns", "action": "hijack-dns"}]


def test_amneziawg_kernel_route_is_source_scoped_and_idempotent() -> None:
    assert AMNEZIAWG_POLICY == {
        "source_cidr": "10.254.0.0/16",
        "table": 10950,
        "priority": 10950,
    }
    assert KERNEL_POLICY_SPECS["amneziawg"] == AMNEZIAWG_POLICY
    script = _kernel_reconcile_script(state_with(amneziawg="outbound"))
    assert "ip -4 route flush table 10950" in script
    assert "priority 10950" in script
    assert "from 10.254.0.0/16 lookup 10950" in script
    assert f"default dev {KERNEL_TUN_NAME} table 10950" in script


def test_standalone_helper_matches_upstream_runtime_contracts() -> None:
    # Compile the exact helper shipped to managed nodes, not a copy.
    compile(STANDALONE_RECONCILE_SCRIPT, "<standalone-policy-reconcile>", "exec")

    # Mieru server egress supports SOCKS5 proxies and wildcard egress rules.
    assert '"protocol": "SOCKS5_PROXY_PROTOCOL"' in STANDALONE_RECONCILE_SCRIPT
    assert '"ipRanges": ["*"]' in STANDALONE_RECONCILE_SCRIPT
    assert '"domainNames": ["*"]' in STANDALONE_RECONCILE_SCRIPT
    assert "socks5UDPAssociate" not in STANDALONE_RECONCILE_SCRIPT
    assert 'canonical = BASE / "mieru" / "server.json"' in STANDALONE_RECONCILE_SCRIPT

    # TrustTunnel uses its documented global SOCKS5 forward protocol.
    assert "[forward_protocol.socks5]" in STANDALONE_RECONCILE_SCRIPT
    assert 'address = \\"127.0.0.1:{TRUST_PORT}\\"' in STANDALONE_RECONCILE_SCRIPT

    # Sudoku future per-subscription services are covered before start by the
    # generator and only process-initiated connections are marked for TPROXY.
    assert "system-generators/twinpanel-sudoku-outbound-policy" in STANDALONE_RECONCILE_SCRIPT
    assert "twinpanel-sudoku*.service" in STANDALONE_RECONCILE_SCRIPT
    assert "User=twinpanel-sudoku" in STANDALONE_RECONCILE_SCRIPT
    assert "CONNMARK" in STANDALONE_RECONCILE_SCRIPT
    assert "--ctstate\", \"NEW" in STANDALONE_RECONCILE_SCRIPT
    assert "TPROXY" in STANDALONE_RECONCILE_SCRIPT
    assert "--uid-owner" in STANDALONE_RECONCILE_SCRIPT


def test_payload_reports_fifteen_supported_and_installed_truthfully() -> None:
    installed = {key: True for key in ALL_PROTOCOL_KEYS}
    rows = _protocol_payload(
        doc=base_doc(),
        state=_clean_state({}),
        default_tag="direct",
        installed_map=installed,
    )
    assert len(rows) == 15
    assert sum(1 for row in rows if row["policy_supported"]) == 15
    assert all(row["installed"] is True for row in rows)
    assert all(row["reason"] is None for row in rows)

    for key in TARGETS:
        assert _effective_outbound(
            protocol=key,
            policy={"mode": "inherit"},
            default_tag="warp",
        ) == "direct"


def test_adapter_spec_ports_are_unique_and_loopback_managed() -> None:
    ports = [int(item["listen_port"]) for item in STANDALONE_POLICY_SPECS.values()]
    assert len(ports) == len(set(ports)) == 3
    assert set(ports) == {19083, 19084, 19085}


def main() -> None:
    tests = [
        test_inventory_is_fifteen_of_fifteen_route_ready,
        test_standalone_rules_are_real_singbox_matches,
        test_reconcile_builds_all_standalone_policy_inbounds,
        test_inherit_removes_standalone_managed_inbounds,
        test_amneziawg_kernel_route_is_source_scoped_and_idempotent,
        test_standalone_helper_matches_upstream_runtime_contracts,
        test_payload_reports_fifteen_supported_and_installed_truthfully,
        test_adapter_spec_ports_are_unique_and_loopback_managed,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS total={len(tests)} route_ready=15/15")


if __name__ == "__main__":
    main()
