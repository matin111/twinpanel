from __future__ import annotations

from app.outbound_policy_native_adapters_v255 import NATIVE_POLICY_INBOUND_TAGS
from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.routers.outbound_policy_center_v1 import (
    _PROTOCOLS,
    _apply_state_to_document,
    _clean_state,
    _generated_rule,
    _protocol_payload,
    _strip_previous_generated_rules,
)
from app.modern_protocol_runtime_v2 import SHADOWTLS_INNER_TAG, TAGS


ROUTE_READY = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
}


def test_adapter_map_matches_runtime_tags() -> None:
    expected = {
        key: TAGS[key]
        for key in ("hysteria2", "tuic", "anytls", "naive", "snell")
    }
    expected["shadowtls"] = SHADOWTLS_INNER_TAG
    assert NATIVE_POLICY_INBOUND_TAGS == expected


def test_full_canonical_protocol_inventory() -> None:
    keys = [str(item["key"]) for item in _PROTOCOLS]
    assert len(keys) == 15
    assert len(set(keys)) == 15
    assert set(keys) == set(ALL_PROTOCOL_KEYS)
    assert keys[:6] == ["hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell"]
    assert {str(item["key"]) for item in _PROTOCOLS if item.get("policy_supported")} == ROUTE_READY
    assert set(NATIVE_POLICY_INBOUND_TAGS) == ROUTE_READY

    by_key = {str(item["key"]): item for item in _PROTOCOLS}
    assert by_key["v2ray"]["plane"] == "xray"
    assert by_key["v2ray"]["core"] == "Xray"
    assert by_key["naive"]["plane"] == "singbox"
    assert by_key["naive"]["policy_supported"] is True
    assert by_key["naive"]["inbound_tag"] == "twinpanel-naive-in"
    assert by_key["shadowtls"]["inbound_tag"] == "twinpanel-shadowtls-inner"
    assert by_key["snell"]["inbound_tag"] == "twinpanel-snell-in"
    assert by_key["mieru"]["plane"] == "standalone"
    assert by_key["trusttunnel"]["plane"] == "standalone"
    assert by_key["amneziawg"]["plane"] == "standalone"
    assert by_key["sudoku"]["plane"] == "standalone"


def test_protocol_payload_keeps_full_inventory_fail_closed() -> None:
    doc = {
        "inbounds": [
            {"type": "hysteria2", "tag": "twinpanel-hysteria2-in"},
            {"type": "tuic", "tag": "twinpanel-tuic-in"},
            {"type": "anytls", "tag": "twinpanel-anytls-in"},
            {"type": "naive", "tag": "twinpanel-naive-in"},
            {
                "type": "shadowtls",
                "tag": "twinpanel-shadowtls-in",
                "detour": "twinpanel-shadowtls-inner",
            },
            {"type": "shadowsocks", "tag": "twinpanel-shadowtls-inner"},
            {"type": "snell", "tag": "twinpanel-snell-in"},
        ],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {"type": "vless", "tag": "ext-vless-primary"},
        ],
        "route": {"final": "ext-vless-primary", "rules": []},
    }
    rows = _protocol_payload(doc=doc, state=_clean_state({}), default_tag="ext-vless-primary")
    assert len(rows) == 15
    by_key = {row["key"]: row for row in rows}
    assert all(by_key[key]["installed"] is True for key in ROUTE_READY)
    assert all(by_key[key]["policy_supported"] is True for key in ROUTE_READY)
    assert by_key["v2ray"]["reason"] == "separate_core_adapter_required"
    assert by_key["mieru"]["reason"] == "protocol_egress_adapter_required"
    assert by_key["cisco"]["policy_supported"] is False
    assert by_key["cisco"]["reason"] == "egress_adapter_required"


def test_native_route_modes() -> None:
    assert _generated_rule("hysteria2", {"mode": "inherit"}) is None
    assert _generated_rule("hysteria2", {"mode": "direct"}) == {
        "inbound": ["twinpanel-hysteria2-in"],
        "action": "route",
        "outbound": "direct",
    }
    assert _generated_rule(
        "tuic",
        {"mode": "outbound", "outbound_tag": "ext-vless-primary"},
    ) == {
        "inbound": ["twinpanel-tuic-in"],
        "action": "route",
        "outbound": "ext-vless-primary",
    }
    assert _generated_rule("anytls", {"mode": "block"}) == {
        "inbound": ["twinpanel-anytls-in"],
        "action": "reject",
        "method": "default",
    }
    assert _generated_rule(
        "naive",
        {"mode": "outbound", "outbound_tag": "ext-vless-primary"},
    ) == {
        "inbound": ["twinpanel-naive-in"],
        "action": "route",
        "outbound": "ext-vless-primary",
    }
    assert _generated_rule("shadowtls", {"mode": "direct"}) == {
        "inbound": ["twinpanel-shadowtls-inner"],
        "action": "route",
        "outbound": "direct",
    }
    assert _generated_rule("snell", {"mode": "block"}) == {
        "inbound": ["twinpanel-snell-in"],
        "action": "reject",
        "method": "default",
    }


def test_non_audited_protocols_fail_closed() -> None:
    unsupported = set(ALL_PROTOCOL_KEYS) - ROUTE_READY
    for protocol in unsupported:
        assert _generated_rule(
            protocol,
            {"mode": "outbound", "outbound_tag": "ext-vless-primary"},
        ) is None
    # Preserve the early UI alias without making Xray writable.
    assert _generated_rule(
        "xray",
        {"mode": "outbound", "outbound_tag": "ext-vless-primary"},
    ) is None


def test_missing_payload_inbound_stays_uninstalled() -> None:
    doc = {
        "inbounds": [
            {"type": "shadowtls", "tag": "twinpanel-shadowtls-in"},
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
        "route": {"rules": []},
    }
    rows = _protocol_payload(doc=doc, state=_clean_state({}), default_tag="direct")
    by_key = {row["key"]: row for row in rows}
    assert by_key["shadowtls"]["policy_supported"] is True
    assert by_key["shadowtls"]["installed"] is False


def test_only_previous_generated_rules_are_removed() -> None:
    old_generated = {
        "inbound": ["twinpanel-hysteria2-in"],
        "action": "route",
        "outbound": "ext-old",
    }
    unrelated_same_inbound = {
        "inbound": ["twinpanel-hysteria2-in"],
        "domain_suffix": ["example.com"],
        "action": "route",
        "outbound": "direct",
    }
    other = {"protocol": "dns", "action": "hijack-dns"}
    result = _strip_previous_generated_rules(
        [old_generated, unrelated_same_inbound, other],
        [old_generated],
    )
    assert result == [unrelated_same_inbound, other]


def test_apply_preserves_final_and_unrelated_rules() -> None:
    old_generated = {
        "inbound": ["twinpanel-hysteria2-in"],
        "action": "route",
        "outbound": "ext-old",
    }
    unrelated = {"protocol": "dns", "action": "hijack-dns"}
    doc = {
        "inbounds": [
            {"type": "hysteria2", "tag": "twinpanel-hysteria2-in"},
            {"type": "tuic", "tag": "twinpanel-tuic-in"},
            {"type": "naive", "tag": "twinpanel-naive-in"},
        ],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {"type": "vless", "tag": "ext-vless-primary"},
        ],
        "route": {
            "final": "ext-vless-primary",
            "rules": [old_generated, unrelated],
        },
    }
    state = _clean_state(
        {
            "policies": {
                "hysteria2": {"mode": "direct"},
                "tuic": {"mode": "block"},
                "naive": {"mode": "outbound", "outbound_tag": "ext-vless-primary"},
            },
            "generated_rules": [old_generated],
        }
    )
    fresh_doc, fresh_state = _apply_state_to_document(
        doc,
        state,
        [old_generated],
    )

    assert fresh_doc["route"]["final"] == "ext-vless-primary"
    assert fresh_doc["route"]["rules"][-1] == unrelated
    assert fresh_doc["route"]["rules"][0] == {
        "inbound": ["twinpanel-hysteria2-in"],
        "action": "route",
        "outbound": "direct",
    }
    assert fresh_doc["route"]["rules"][1] == {
        "inbound": ["twinpanel-tuic-in"],
        "action": "reject",
        "method": "default",
    }
    assert fresh_doc["route"]["rules"][2] == {
        "inbound": ["twinpanel-naive-in"],
        "action": "route",
        "outbound": "ext-vless-primary",
    }
    assert fresh_state["generated_rules"] == fresh_doc["route"]["rules"][:3]


def main() -> None:
    tests = [
        test_adapter_map_matches_runtime_tags,
        test_full_canonical_protocol_inventory,
        test_protocol_payload_keeps_full_inventory_fail_closed,
        test_native_route_modes,
        test_non_audited_protocols_fail_closed,
        test_missing_payload_inbound_stays_uninstalled,
        test_only_previous_generated_rules_are_removed,
        test_apply_preserves_final_and_unrelated_rules,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS total={len(tests)}")


if __name__ == "__main__":
    main()
