from __future__ import annotations

import os
from types import SimpleNamespace

# Match the public CI-only settings already used by api-build.yml. The smoke
# never connects to the database; these values only allow normal application
# modules to import through Settings/database initialization.
os.environ.setdefault(
    "APP_SECRET_KEY",
    "ci-only-secret-key-ci-only-secret-key-ci-only-secret-key",
)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://twinpanel:twinpanel_test@127.0.0.1:5432/twinpanel",
)
os.environ.setdefault(
    "NODE_AGENT_SHARED_SECRET",
    "ci-node-agent-secret-ci-node-agent-secret",
)

from app import xray_customer_profile_policy_v30 as policy
from app import xray_modern_runtime
from app import xray_tcp_tls_v39
from app.protocol_catalog import PROTOCOL_CATALOG
from app.routers import account_delivery


class FakeDB:
    def __init__(self, node):
        self.node = node

    def get(self, model, node_id):
        if int(node_id) == int(self.node.id):
            return self.node
        return None


def vless(profile: str, port: int) -> dict:
    return {
        "id": profile,
        "title": profile,
        "uri": (
            "vless://11111111-1111-1111-1111-111111111111"
            f"@204.10.192.96:{port}?encryption=none&type=tcp#fixture"
        ),
    }


def main() -> None:
    # Mirror the real self_hosted_runtime composition order: V39 registers the
    # TCP TLS profile in PROFILE_META before V30/V261 isolates target ports.
    xray_tcp_tls_v39.apply_xray_tcp_tls_v39()
    policy._apply_tls_target_isolation_v261()

    assert (
        xray_modern_runtime.PROFILE_META[
            xray_modern_runtime.PROFILE_WS
        ]["offset"]
        == 1001
    )
    assert (
        xray_modern_runtime.PROFILE_META[
            xray_modern_runtime.PROFILE_HTTPUPGRADE
        ]["offset"]
        == 1002
    )
    assert (
        xray_modern_runtime.PROFILE_META[policy.PROFILE_TCP_TLS]["offset"]
        == 1003
    )
    assert xray_tcp_tls_v39.TCP_TLS_OFFSET == 1003

    base_port = 8443
    tls_targets = {
        xray_modern_runtime._target_port(base_port, profile)
        for profile in policy.PUBLIC_PROFILE_ORDER
    }
    assert tls_targets == {9444, 9445, 9446}, tls_targets

    modern_runtime_ports = {
        int(meta.get("default_port") or 0)
        for meta in PROTOCOL_CATALOG.values()
        if int(meta.get("default_port") or 0) > 0
    }
    assert tls_targets.isdisjoint(modern_runtime_ports), (
        tls_targets,
        modern_runtime_ports,
    )

    # Production self-hosted composition remaps these public ranges before V30.
    xray_modern_runtime.PROFILE_META[
        xray_modern_runtime.PROFILE_WS
    ]["public_base"] = 26000
    xray_modern_runtime.PROFILE_META[
        xray_modern_runtime.PROFILE_HTTPUPGRADE
    ]["public_base"] = 27000
    xray_modern_runtime.PROFILE_META[
        policy.PROFILE_TCP_TLS
    ]["public_base"] = 28000

    node = SimpleNamespace(
        id=6,
        public_ip="204.10.192.96",
        public_domain=None,
    )
    db = FakeDB(node)

    original_qr = account_delivery._qr_data_uri
    original_node_host = account_delivery._node_host
    original_port = account_delivery._port

    account_delivery._qr_data_uri = lambda value: "qr:" + str(len(value))
    account_delivery._node_host = lambda current: current.public_ip
    account_delivery._port = lambda current_db, node_id, protocol: 8443

    try:
        tunnel_item = {
            "node_id": 6,
            "server": "193.39.9.222",
            "server_ip": "193.39.9.222",
            "port": 24006,
            "delivery_mode": "tunnel",
            "profiles": [
                vless("xhttp_reality", 24006),
                vless("grpc_reality", 25006),
                vless("websocket_tls", 26006),
                vless("httpupgrade_tls", 27006),
                vless("tcp_tls", 28006),
            ],
        }

        delivered = policy._customer_xray_item_v261(db, tunnel_item)
        assert delivered is not None
        assert delivered["profile"] == "websocket_tls"
        assert delivered["server"] == "193.39.9.222"
        assert delivered["port"] == 26006
        assert "@193.39.9.222:26006?" in delivered["uri"]
        assert {
            profile["id"] for profile in delivered["profiles"]
        } == {
            "websocket_tls",
            "httpupgrade_tls",
            "tcp_tls",
        }
        assert "24006" not in str(delivered)
        assert "25006" not in str(delivered)

        # A modern credential which contains only internal profiles must not
        # fall back to the unrouted XHTTP endpoint.
        hidden_only = dict(tunnel_item)
        hidden_only["profiles"] = [
            vless("xhttp_reality", 24006),
            vless("grpc_reality", 25006),
        ]
        assert policy._customer_xray_item_v261(db, hidden_only) is None

        # Explicit direct delivery keeps the Exit host and uses the isolated
        # private Xray target port instead of the modern 8444..8452 range.
        direct_item = dict(tunnel_item)
        direct_item["server"] = "204.10.192.96"
        direct_item["server_ip"] = "204.10.192.96"
        direct_item["delivery_mode"] = "direct"
        direct_item["profiles"] = [vless("websocket_tls", 8446)]

        direct = policy._customer_xray_item_v261(db, direct_item)
        assert direct is not None
        assert direct["server"] == "204.10.192.96"
        assert direct["port"] == 9444
        assert "@204.10.192.96:9444?" in direct["uri"]

        # Migration compatibility: true legacy credentials without profiles[]
        # keep their historical single VLESS item.
        legacy = {
            "node_id": 6,
            "server": "193.39.9.222",
            "port": 23006,
            "uri": (
                "vless://11111111-1111-1111-1111-111111111111"
                "@193.39.9.222:23006?encryption=none&type=tcp#legacy"
            ),
        }
        assert policy._customer_xray_item_v261(db, legacy) == legacy

        # Payload filtering is Xray-only. A healthy non-Xray credential must
        # remain byte-for-byte equivalent while hidden-only Xray is removed.
        payload = {
            "subscription_id": 17,
            "credentials": [
                {
                    "protocol": "openvpn",
                    "items": [{"node_id": 6, "server": "193.39.9.222"}],
                },
                {
                    "protocol": "v2ray",
                    "items": [hidden_only],
                },
            ],
        }
        filtered = policy._enforce_customer_xray_payload_v261(db, payload)
        assert len(filtered["credentials"]) == 1
        assert filtered["credentials"][0]["protocol"] == "openvpn"
        assert filtered["credentials"][0]["items"][0]["server"] == "193.39.9.222"

    finally:
        account_delivery._qr_data_uri = original_qr
        account_delivery._node_host = original_node_host
        account_delivery._port = original_port

    print("XRAY_CUSTOMER_DELIVERY_V261_OK")


if __name__ == "__main__":
    main()
