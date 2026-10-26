from __future__ import annotations

from app.outbound_policy_native_adapters_v255 import NATIVE_POLICY_INBOUND_TAGS
from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.routers.outbound_policy_center_v2 import (
    KERNEL_POLICY_SPECS,
    KERNEL_TUN_NAME,
    KERNEL_TUN_TAG,
    POLICY_SCHEMA,
    XRAY_BLOCK_OUTBOUND_TAG,
    XRAY_BRIDGE_INBOUND_TAG,
    XRAY_BRIDGE_OUTBOUND_TAG,
    _PROTOCOLS,
    _apply_state_to_document,
    _apply_xray_policy_to_document,
    _clean_state,
    _effective_outbound,
    _generated_rule,
    _kernel_reconcile_script,
    _policy_record,
    _protocol_payload,
    _strip_previous_generated_rules,
)

ROUTE_READY = {
    "hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell",
    "cisco", "openvpn", "wireguard", "l2tp", "v2ray",
}
PENDING = {"mieru", "trusttunnel", "amneziawg", "sudoku"}


def base_doc() -> dict:
    return {
        "inbounds": [
            *[{"type": "test", "tag": tag} for tag in NATIVE_POLICY_INBOUND_TAGS.values()],
        ],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {"type": "vless", "tag": "ext-vless-primary"},
        ],
        "route": {
            "final": "ext-vless-primary",
            "rules": [{"protocol": "dns", "action": "hijack-dns"}],
        },
    }


def xray_doc() -> dict:
    return {
        "inbounds": [
            {"tag": "vless-in", "protocol": "vless", "settings": {"clients": []}},
            {"tag": "api", "protocol": "dokodemo-door", "settings": {}},
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}],
        "routing": {
            "rules": [
                {"type": "field", "inboundTag": ["api"], "outboundTag": "api"}
            ]
        },
    }


def test_inventory_is_full_and_truthful() -> None:
    keys = [str(item["key"]) for item in _PROTOCOLS]
    assert len(keys) == 15
    assert len(set(keys)) == 15
    assert set(keys) == set(ALL_PROTOCOL_KEYS)
    assert {str(x["key"]) for x in _PROTOCOLS if x.get("policy_supported")} == ROUTE_READY

    by_key = {str(item["key"]): item for item in _PROTOCOLS}
    for key in ("cisco", "openvpn", "wireguard", "l2tp"):
        assert by_key[key]["adapter_kind"] == "kernel-tun"
        assert by_key[key]["plane"] == "kernel"
    assert by_key["v2ray"]["adapter_kind"] == "xray-bridge"
    assert by_key["v2ray"]["plane"] == "xray"
    for key in PENDING:
        assert by_key[key]["policy_supported"] is False
        assert by_key[key]["reason"] == "runtime_core_pending"


def test_state_v1_migrates_without_losing_policies() -> None:
    state = _clean_state(
        {
            "schema": 1,
            "policies": {"hysteria2": {"mode": "direct"}},
            "generated_rules": [{"inbound": ["x"], "action": "route", "outbound": "direct"}],
        }
    )
    assert state["schema"] == POLICY_SCHEMA
    assert _policy_record(state, "hysteria2")["mode"] == "direct"
    assert state["xray_generated_rules"] == []
    assert state["xray_generated_outbounds"] == []


def test_kernel_rule_matches_real_vpn_source_subnets() -> None:
    assert _generated_rule("cisco", {"mode": "direct"}) == {
        "source_ip_cidr": ["10.91.0.0/24"],
        "action": "route",
        "outbound": "direct",
    }
    assert _generated_rule(
        "openvpn", {"mode": "outbound", "outbound_tag": "ext-vless-primary"}
    ) == {
        "source_ip_cidr": ["10.92.0.0/24"],
        "action": "route",
        "outbound": "ext-vless-primary",
    }
    assert _generated_rule("wireguard", {"mode": "block"}) == {
        "source_ip_cidr": ["10.93.0.0/24"],
        "action": "reject",
        "method": "default",
    }
    assert _generated_rule("l2tp", {"mode": "inherit"}) is None


def test_xray_bridge_rule_exists_only_for_external_outbound() -> None:
    assert _generated_rule("v2ray", {"mode": "inherit"}) is None
    assert _generated_rule("v2ray", {"mode": "direct"}) is None
    assert _generated_rule("v2ray", {"mode": "block"}) is None
    assert _generated_rule(
        "v2ray", {"mode": "outbound", "outbound_tag": "ext-vless-primary"}
    ) == {
        "inbound": [XRAY_BRIDGE_INBOUND_TAG],
        "action": "route",
        "outbound": "ext-vless-primary",
    }


def test_singbox_managed_inbounds_are_bounded_and_removed_on_inherit() -> None:
    doc = base_doc()
    state = _clean_state(
        {
            "policies": {
                "openvpn": {"mode": "outbound", "outbound_tag": "ext-vless-primary"},
                "v2ray": {"mode": "outbound", "outbound_tag": "ext-vless-primary"},
            }
        }
    )
    fresh, fresh_state = _apply_state_to_document(doc, state, [])
    by_tag = {
        item.get("tag"): item for item in fresh["inbounds"] if isinstance(item, dict)
    }
    assert by_tag[KERNEL_TUN_TAG]["type"] == "tun"
    assert by_tag[KERNEL_TUN_TAG]["interface_name"] == KERNEL_TUN_NAME
    assert by_tag[KERNEL_TUN_TAG]["auto_route"] is False
    assert by_tag[XRAY_BRIDGE_INBOUND_TAG]["type"] == "socks"
    assert by_tag[XRAY_BRIDGE_INBOUND_TAG]["listen"] == "127.0.0.1"

    rules = fresh["route"]["rules"]
    assert rules[0] == {
        "source_ip_cidr": ["10.92.0.0/24"],
        "action": "route",
        "outbound": "ext-vless-primary",
    }
    assert rules[1] == {
        "inbound": [XRAY_BRIDGE_INBOUND_TAG],
        "action": "route",
        "outbound": "ext-vless-primary",
    }
    assert rules[-1] == {"protocol": "dns", "action": "hijack-dns"}

    inherit = _clean_state(fresh_state)
    inherit["policies"]["openvpn"] = {"mode": "inherit", "outbound_tag": None}
    inherit["policies"]["v2ray"] = {"mode": "inherit", "outbound_tag": None}
    restored, _ = _apply_state_to_document(
        fresh, inherit, list(fresh_state["generated_rules"])
    )
    restored_tags = {
        item.get("tag") for item in restored["inbounds"] if isinstance(item, dict)
    }
    assert KERNEL_TUN_TAG not in restored_tags
    assert XRAY_BRIDGE_INBOUND_TAG not in restored_tags
    assert restored["route"]["rules"] == [{"protocol": "dns", "action": "hijack-dns"}]


def test_xray_direct_block_and_bridge_preserve_unrelated_config() -> None:
    base = xray_doc()

    direct_state = _clean_state({"policies": {"v2ray": {"mode": "direct"}}})
    direct_doc, direct_state = _apply_xray_policy_to_document(base, direct_state)
    assert direct_doc["routing"]["rules"][0] == {
        "type": "field",
        "inboundTag": ["vless-in"],
        "outboundTag": "direct",
    }
    assert direct_doc["routing"]["rules"][-1]["inboundTag"] == ["api"]

    block_state = _clean_state(direct_state)
    block_state["policies"]["v2ray"] = {"mode": "block"}
    block_doc, block_state = _apply_xray_policy_to_document(direct_doc, block_state)
    assert block_doc["routing"]["rules"][0]["outboundTag"] == XRAY_BLOCK_OUTBOUND_TAG
    assert block_doc["outbounds"][0] == {
        "protocol": "blackhole",
        "tag": XRAY_BLOCK_OUTBOUND_TAG,
        "settings": {},
    }
    assert any(x.get("tag") == "direct" for x in block_doc["outbounds"])

    bridge_state = _clean_state(block_state)
    bridge_state["policies"]["v2ray"] = {
        "mode": "outbound",
        "outbound_tag": "ext-vless-primary",
    }
    bridge_doc, bridge_state = _apply_xray_policy_to_document(block_doc, bridge_state)
    assert bridge_doc["routing"]["rules"][0]["outboundTag"] == XRAY_BRIDGE_OUTBOUND_TAG
    assert bridge_doc["outbounds"][0] == {
        "protocol": "socks",
        "tag": XRAY_BRIDGE_OUTBOUND_TAG,
        "settings": {"address": "127.0.0.1", "port": 19081},
    }
    assert all(x.get("tag") != XRAY_BLOCK_OUTBOUND_TAG for x in bridge_doc["outbounds"])

    inherit_state = _clean_state(bridge_state)
    inherit_state["policies"]["v2ray"] = {"mode": "inherit"}
    inherit_doc, inherit_state = _apply_xray_policy_to_document(bridge_doc, inherit_state)
    assert inherit_doc == base
    assert inherit_state["xray_generated_rules"] == []
    assert inherit_state["xray_generated_outbounds"] == []


def test_kernel_script_is_idempotent_and_private_safe() -> None:
    state = _clean_state(
        {"policies": {"cisco": {"mode": "direct"}, "wireguard": {"mode": "block"}}}
    )
    script = _kernel_reconcile_script(state)
    for spec in KERNEL_POLICY_SPECS.values():
        assert f"ip -4 route flush table {spec['table']}" in script
        assert f"priority {spec['priority']}" in script
    assert "from 10.91.0.0/24 lookup 10910" in script
    assert "from 10.93.0.0/24 lookup 10930" in script
    assert "from 10.92.0.0/24 lookup 10920" not in script
    assert "throw 10.0.0.0/8 table 10910" in script
    assert f"default dev {KERNEL_TUN_NAME} table 10930" in script


def test_effective_path_does_not_lie_for_unmanaged_classic_inherit() -> None:
    assert _effective_outbound(
        protocol="openvpn", policy={"mode": "inherit"}, default_tag="ext-vless-primary"
    ) == "direct"
    assert _effective_outbound(
        protocol="v2ray", policy={"mode": "inherit"}, default_tag="ext-vless-primary"
    ) == "direct"
    assert _effective_outbound(
        protocol="hysteria2", policy={"mode": "inherit"}, default_tag="ext-vless-primary"
    ) == "ext-vless-primary"


def test_payload_reports_eleven_supported_without_faking_pending_cores() -> None:
    installed = {key: True for key in ROUTE_READY}
    rows = _protocol_payload(
        doc=base_doc(),
        state=_clean_state({}),
        default_tag="direct",
        installed_map=installed,
    )
    by_key = {row["key"]: row for row in rows}
    assert len(rows) == 15
    assert sum(1 for row in rows if row["policy_supported"]) == 11
    assert all(by_key[key]["installed"] is True for key in ROUTE_READY)
    assert all(by_key[key]["installed"] is None for key in PENDING)
    assert all(by_key[key]["reason"] == "runtime_core_pending" for key in PENDING)


def test_exact_rule_removal_still_preserves_user_rules() -> None:
    generated = {
        "source_ip_cidr": ["10.91.0.0/24"],
        "action": "route",
        "outbound": "direct",
    }
    unrelated = {
        "source_ip_cidr": ["10.91.0.0/24"],
        "domain_suffix": ["example.com"],
        "action": "route",
        "outbound": "direct",
    }
    assert _strip_previous_generated_rules([generated, unrelated], [generated]) == [unrelated]


def main() -> None:
    tests = [
        test_inventory_is_full_and_truthful,
        test_state_v1_migrates_without_losing_policies,
        test_kernel_rule_matches_real_vpn_source_subnets,
        test_xray_bridge_rule_exists_only_for_external_outbound,
        test_singbox_managed_inbounds_are_bounded_and_removed_on_inherit,
        test_xray_direct_block_and_bridge_preserve_unrelated_config,
        test_kernel_script_is_idempotent_and_private_safe,
        test_effective_path_does_not_lie_for_unmanaged_classic_inherit,
        test_payload_reports_eleven_supported_without_faking_pending_cores,
        test_exact_rule_removal_still_preserves_user_rules,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS total={len(tests)}")


if __name__ == "__main__":
    main()
