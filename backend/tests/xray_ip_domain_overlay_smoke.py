"""Keep verified Iran VLESS IP Address through the dedicated-domain overlay.

This regression reproduces the production /sub bug: account_delivery correctly
selected the real Iran IP but xray_node_domain_runtime then replaced it with
Cloudflare-proxied dedicated xray_domain on matching DNS records.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault(
    "APP_SECRET_KEY", "ci-only-secret-key-ci-only-secret-key-ci-only-secret-key"
)
_folder = tempfile.TemporaryDirectory(prefix="xray-domain-ip-smoke-")
os.environ["DATABASE_URL"] = (
    f"sqlite+pysqlite:///{Path(_folder.name) / 'bootstrap.sqlite3'}"
)
os.environ.setdefault(
    "NODE_AGENT_SHARED_SECRET", "ci-only-node-secret-ci-only-node-secret"
)

from app import xray_node_domain_runtime as runtime
from app import xray_modern_runtime


def main() -> None:
    node = SimpleNamespace(
        id=6,
        xray_domain="v2ray1.in88.sbs",
        public_domain="tunel1.in88.sbs",
        public_ip="204.10.192.96",
    )

    old_resolver = runtime._resolved_host_ips
    old_profile = runtime._original_profile_endpoint
    old_explicit = runtime._original_customer_profile_endpoint_v261
    old_port = xray_modern_runtime._public_port

    try:
        # Demonstrates why DNS-based "same ingress" is insufficient: DNS may
        # later be proxied/poisoned. IP authority must stay an IP.
        runtime._resolved_host_ips = lambda host, bucket: frozenset(
            {"193.39.9.222"}
        )
        assert runtime._verified_tunnel_xray_domain(
            node, "193.39.9.222"
        ) == "193.39.9.222"

        # Preserve previous behavior when the caller deliberately sends a
        # hostname rather than an explicit routable IP.
        assert runtime._verified_tunnel_xray_domain(
            node, "tunel1.in88.sbs"
        ) == "v2ray1.in88.sbs"

        runtime._original_profile_endpoint = (
            lambda db, current_node, profile: ("193.39.9.222", 26006)
        )
        xray_modern_runtime._public_port = lambda node_id, profile: 26006
        assert runtime._profile_endpoint_with_dedicated_domain(
            None, node, "websocket_tls"
        ) == ("193.39.9.222", 26006)

        runtime._original_customer_profile_endpoint_v261 = (
            lambda db, current_node, profile, item: ("193.39.9.222", 26006)
        )
        assert runtime._customer_profile_endpoint_with_dedicated_domain(
            None, node, "websocket_tls", {"delivery_mode": "tunnel"}
        ) == ("193.39.9.222", 26006)

        # Direct-mode subscriptions must keep the explicitly configured TLS
        # domain. This fix is NOT a global TLS/SNI or endpoint rewrite.
        runtime._original_customer_profile_endpoint_v261 = (
            lambda db, current_node, profile, item: ("204.10.192.96", 9444)
        )
        assert runtime._customer_profile_endpoint_with_dedicated_domain(
            None, node, "websocket_tls", {"delivery_mode": "direct"}
        ) == ("v2ray1.in88.sbs", 9444)

    finally:
        runtime._resolved_host_ips = old_resolver
        runtime._original_profile_endpoint = old_profile
        runtime._original_customer_profile_endpoint_v261 = old_explicit
        xray_modern_runtime._public_port = old_port

    print("TWINPANEL_XRAY_IP_DOMAIN_OVERLAY_SMOKE=PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        _folder.cleanup()
