from __future__ import annotations

from app.routers.outbound_policy_center_v1 import (
    _apply_state_to_document,
    _clean_state,
    _generated_rule,
    _strip_previous_generated_rules,
)


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


def test_classic_protocols_fail_closed() -> None:
    for protocol in ("openvpn", "wireguard", "cisco", "l2tp", "xray"):
        assert _generated_rule(
            protocol,
            {"mode": "outbound", "outbound_tag": "ext-vless-primary"},
        ) is None


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
    assert fresh_state["generated_rules"] == fresh_doc["route"]["rules"][:2]


def main() -> None:
    tests = [
        test_native_route_modes,
        test_classic_protocols_fail_closed,
        test_only_previous_generated_rules_are_removed,
        test_apply_preserves_final_and_unrelated_rules,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS total={len(tests)}")


if __name__ == "__main__":
    main()
