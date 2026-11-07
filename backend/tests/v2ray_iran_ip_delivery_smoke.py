"""Regression: VLESS Iran tunnel address uses direct IP, never a proxied A record.

Run: python backend/tests/v2ray_iran_ip_delivery_smoke.py
No database, network, user credentials, or real tunnel mutations are involved.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("APP_SECRET_KEY", "ci-only-secret-key-ci-only-secret-key-ci-only-secret-key")
_folder = tempfile.TemporaryDirectory(prefix="v2ray-ip-smoke-")
os.environ["DATABASE_URL"] = (
    f"sqlite+pysqlite:///{Path(_folder.name) / 'bootstrap.sqlite3'}"
)
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "ci-only-node-secret-ci-only-node-secret")

from app.models import Node, NodeStatus, NodeType, Tunnel, TunnelStatus
from app.routers import account_delivery
from app import xray_customer_profile_policy_v30 as customer_policy
from app import xray_modern_runtime


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return None


class FakeDB:
    def __init__(self, nodes, tunnels):
        self.nodes = {int(x.id): x for x in nodes}
        self.tunnels = {int(x.id): x for x in tunnels}

    def get(self, model, ident):
        if model is Node:
            return self.nodes.get(int(ident))
        if model is Tunnel:
            return self.tunnels.get(int(ident))
        return None

    def query(self, model):
        if model is Tunnel:
            return FakeQuery(list(self.tunnels.values()))
        return FakeQuery([])


def main():
    iran = SimpleNamespace(
        id=2, node_type=NodeType.IRAN, public_ip="193.39.9.222",
        public_domain="vtray.in88.sbs", agent_url="https://example.test",
        retired_at=None, is_mother=False, status=NodeStatus.ONLINE,
    )
    exit_node = SimpleNamespace(
        id=6, node_type=NodeType.EXIT, public_ip="204.10.192.96",
        public_domain="exit.example.test", xray_domain=None, retired_at=None,
    )
    tunnel = SimpleNamespace(
        id=6, iran_node_id=2, exit_node_id=6,
        priority=1, is_active=True, status=TunnelStatus.ONLINE,
    )
    db = FakeDB([iran, exit_node], [tunnel])

    assert account_delivery._v2ray_iran_public_ip(iran) == "193.39.9.222"
    assert account_delivery._tunnel_access_endpoint(db, exit_node, "v2ray") == (
        "193.39.9.222", 23006,
    )
    # Do not mutate Cisco/OpenVPN/WireGuard/L2TP domain delivery.
    assert account_delivery._tunnel_access_endpoint(db, exit_node, "openvpn") == (
        "vtray.in88.sbs", 21006,
    )

    # Modern VLESS security layer SNI and WS Host are independent from
    # connect address, as they must be when using raw IPv4.
    host, port = xray_modern_runtime._profile_endpoint(
        db, exit_node, xray_modern_runtime.PROFILE_WS
    )
    assert host == "193.39.9.222"
    assert port == xray_modern_runtime._public_port(exit_node.id, "websocket_tls")

    # Old explicit-policy subscriptions may store Cloudflare hostnames.
    # Only their tunnel address is resolved to the selected real ingress.
    item = {
        "delivery_mode": "tunnel", "tunnel_id": 6,
        "server": "vtray.in88.sbs", "server_ip": "vtray.in88.sbs",
    }
    assert customer_policy._profile_endpoint_v261(
        db, exit_node, "websocket_tls", item
    )[0] == "193.39.9.222"

    # Legacy one-tunnel explicit assignment without tunnel_id also converges.
    item.pop("tunnel_id")
    assert customer_policy._profile_endpoint_v261(
        db, exit_node, "websocket_tls", item
    )[0] == "193.39.9.222"

    # A direct-mode subscriber must not be silently routed via Iran.
    item["delivery_mode"] = "direct"
    assert customer_policy._profile_endpoint_v261(
        db, exit_node, "websocket_tls", item
    )[0] == "exit.example.test"

    # Never publish a private/loopback IPv4 as a public VPN endpoint.
    iran.public_ip = "10.10.34.35"
    assert account_delivery._v2ray_iran_public_ip(iran) is None
    assert account_delivery._tunnel_access_endpoint(db, exit_node, "v2ray") == (
        "vtray.in88.sbs", 23006,
    )

    # With two candidate tunnels, preserve explicit mapping and never
    # guess a different Iran server when the saved host does not match.
    iran.public_ip = "193.39.9.222"
    alternate = SimpleNamespace(
        id=9, node_type=NodeType.IRAN, public_ip="94.183.231.158",
        public_domain="v2ray2.in88.sbs", retired_at=None, is_mother=False,
        status=NodeStatus.ONLINE,
    )
    db.nodes[9] = alternate
    db.tunnels[40] = SimpleNamespace(
        id=40, iran_node_id=9, exit_node_id=6,
        priority=2, is_active=True, status=TunnelStatus.ONLINE,
    )
    item["delivery_mode"] = "tunnel"
    item["server"] = "v2ray2.in88.sbs"
    assert customer_policy._profile_endpoint_v261(
        db, exit_node, "websocket_tls", item
    )[0] == "94.183.231.158"
    item["server"] = "unknown-proxy.example"
    assert customer_policy._profile_endpoint_v261(
        db, exit_node, "websocket_tls", item
    )[0] == "unknown-proxy.example"

    print("TWINPANEL_V2RAY_IRAN_IP_DELIVERY_SMOKE=PASS")


if __name__ == "__main__":
    try:
        main()
    finally:
        _folder.cleanup()
