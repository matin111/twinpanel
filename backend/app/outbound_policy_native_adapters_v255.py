from __future__ import annotations

from .modern_protocol_runtime_v2 import SHADOWTLS_INNER_TAG, TAGS


# Explicit allow-list of protocol runtimes whose payload traffic is already
# inside TwinPanel's managed sing-box service and therefore can be routed by
# the Outbound Policy Center without crossing kernel/Xray/standalone planes.
#
# Keep this list explicit: a future protocol appearing in Protocol Studio must
# not become route-writable merely because it happens to use sing-box.
_NATIVE_DIRECT_INBOUND_PROTOCOLS: tuple[str, ...] = (
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "snell",
)


NATIVE_POLICY_INBOUND_TAGS: dict[str, str] = {
    key: TAGS[key]
    for key in _NATIVE_DIRECT_INBOUND_PROTOCOLS
}

# ShadowTLS v3 is a camouflage transport. Authenticated traffic is detoured
# into the dedicated managed inner Shadowsocks inbound, so policy matching must
# happen on that payload inbound rather than on the outer TLS camouflage tag.
NATIVE_POLICY_INBOUND_TAGS["shadowtls"] = SHADOWTLS_INNER_TAG


ROUTE_READY_SINGBOX_PROTOCOLS = frozenset(NATIVE_POLICY_INBOUND_TAGS)
