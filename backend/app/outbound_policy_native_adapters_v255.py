from __future__ import annotations


# Explicit audited allow-list of payload inbounds which already live inside
# TwinPanel's managed sing-box process. Keep this module dependency-free:
# modern_protocol_runtime_v2 imports provisioning routers, while the Outbound
# Policy router imports this map during router package initialization. Importing
# the runtime here would therefore create a circular startup dependency.
#
# Drift against the runtime's canonical TAGS/SHADOWTLS_INNER_TAG constants is
# enforced by outbound_policy_center_v1_smoke.py.
NATIVE_POLICY_INBOUND_TAGS: dict[str, str] = {
    "hysteria2": "twinpanel-hysteria2-in",
    "tuic": "twinpanel-tuic-in",
    "anytls": "twinpanel-anytls-in",
    "naive": "twinpanel-naive-in",
    "snell": "twinpanel-snell-in",
    # ShadowTLS v3 is only camouflage. Authenticated payload traffic is
    # detoured into this dedicated managed inner Shadowsocks inbound.
    "shadowtls": "twinpanel-shadowtls-inner",
}


ROUTE_READY_SINGBOX_PROTOCOLS = frozenset(NATIVE_POLICY_INBOUND_TAGS)
