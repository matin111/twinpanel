"""Partial TLS profile sets must not hide independently usable inbounds."""
from app.xray_adaptive_three_profiles_v47 import (
    _customer_order_for_item,
    _customer_profiles_v47,
)
from app import xray_modern_runtime

WS = xray_modern_runtime.PROFILE_WS
XHTTP = xray_modern_runtime.PROFILE_XHTTP


def _item(*profiles):
    return {"profiles": [{"id": p, "uri": f"vless://user@host:443#{p}"} for p in profiles]}


def test_websocket_tls_visible_even_if_tcp_tls_not_created_yet():
    profiles = _customer_profiles_v47(_item(WS, XHTTP))
    assert [p["id"] for p in profiles] == [WS, XHTTP]


def test_ready_tls_profiles_exclude_stale_tcp_reality():
    profiles = _customer_profiles_v47(_item(WS, XHTTP, "tcp_reality"))
    assert [p["id"] for p in profiles] == [WS, XHTTP]


def test_complete_tls_trio_keeps_expected_order():
    profiles = _customer_profiles_v47(_item(WS, XHTTP, "tcp_tls"))
    assert [p["id"] for p in profiles] == [WS, XHTTP, "tcp_tls"]


def test_domainless_reality_profiles_keep_their_order():
    profiles = _customer_profiles_v47(_item(XHTTP, "tcp_reality"))
    assert [p["id"] for p in profiles] == [XHTTP, "tcp_reality"]


def test_only_ready_profiles_appear_no_synthetic_link():
    profiles = _customer_profiles_v47(_item(XHTTP))
    assert [p["id"] for p in profiles] == [XHTTP]
