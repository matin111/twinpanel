"""Regression: centrally registered Sudoku must use ONE shared tunnel route.

Never modify services, data, credentials or connections. Legacy exits must keep
their existing routes until customer configs are migrated deliberately.
"""
from __future__ import annotations

import base64
import json
from types import SimpleNamespace

from app import modern_protocol_tunnel_binding_v251 as binding


def test_central_shared_exit_has_one_route_for_all_users():
    node = SimpleNamespace(id=19, node_type=binding.NodeType.EXIT,
                           public_ip="192.0.2.19", public_domain=None,
                           retired_at=None, show_to_users=True)
    original_cfg = binding._configured_modern_protocols
    original_shared = binding._sudoku_shared_exit
    original_ids = binding._sudoku_desired_subscription_ids
    try:
        binding._configured_modern_protocols = lambda db, nid: {
            "sudoku": SimpleNamespace(status="online")
        }
        binding._sudoku_shared_exit = lambda db, n: True
        # If the optimized shared branch accidentally enumerates users, fail.
        binding._sudoku_desired_subscription_ids = lambda db: (_ for _ in ()).throw(
            AssertionError("shared route may not enumerate subscriptions")
        )
        got = binding._modern_routes_for_exit(None, node, "10.253.0.19")
        assert got == [{
            "protocol": "sudoku",
            "profile": "shared",
            "exit_node_id": 19,
            "public_port": 50019,
            "target_ip": "10.253.0.19",
            "target_port": 18553,
            "transport": "tcp",
            "client_subnet": None,
        }]
    finally:
        binding._configured_modern_protocols = original_cfg
        binding._sudoku_shared_exit = original_shared
        binding._sudoku_desired_subscription_ids = original_ids


def test_public_shared_endpoint_matches_its_tunnel_route():
    node = SimpleNamespace(id=22, node_type=binding.NodeType.EXIT,
                           public_ip="192.0.2.22", public_domain=None,
                           retired_at=None, show_to_users=True)
    iran = SimpleNamespace(id=23, public_ip="192.0.2.23", public_domain=None)
    cfg = binding._configured_modern_protocols
    selected = binding._selected_iran_node
    shared = binding._sudoku_shared_exit
    try:
        binding._configured_modern_protocols = lambda db, nid: {
            "sudoku": SimpleNamespace(status="online")
        }
        binding._selected_iran_node = lambda db, n: iran
        binding._sudoku_shared_exit = lambda db, n: True
        assert binding._modern_tunnel_endpoint(None, node, "sudoku", 19) == (
            "192.0.2.23", 50022
        )
        assert binding._modern_tunnel_endpoint(None, node, "sudoku", 1555) == (
            "192.0.2.23", 50022
        )
        binding._configured_modern_protocols = lambda db, nid: {
            "sudoku": SimpleNamespace(status="offline")
        }
        assert binding._modern_tunnel_endpoint(None, node, "sudoku", 19) is None
    finally:
        binding._configured_modern_protocols = cfg
        binding._selected_iran_node = selected
        binding._sudoku_shared_exit = shared


def test_retired_legacy_exit_generates_no_sudoku_routes():
    node = SimpleNamespace(id=6, node_type=binding.NodeType.EXIT,
                           public_ip="192.0.2.6", public_domain=None,
                           retired_at=None, show_to_users=True)
    cfg = binding._configured_modern_protocols
    shared = binding._sudoku_shared_exit
    ids = binding._sudoku_desired_subscription_ids
    mapping = binding._sudoku_public_port_map
    try:
        binding._configured_modern_protocols = lambda db, nid: {
            "sudoku": SimpleNamespace(status="online")
        }
        binding._sudoku_shared_exit = lambda db, n: False
        binding._sudoku_desired_subscription_ids = lambda db: (_ for _ in ()).throw(
            AssertionError("legacy subscriptions must not be enumerated")
        )
        binding._sudoku_public_port_map = lambda db: (_ for _ in ()).throw(
            AssertionError("retired NAT ports must never be calculated")
        )
        routes = binding._modern_routes_for_exit(None, node, "10.253.0.6")
        assert routes == []
    finally:
        binding._configured_modern_protocols = cfg
        binding._sudoku_shared_exit = shared
        binding._sudoku_desired_subscription_ids = ids
        binding._sudoku_public_port_map = mapping


def test_shared_rewrite_preserves_private_key():
    data = {"n": "test", "h": "192.0.2.22", "p": 18553, "k": "test-key", "e": "chacha20-poly1305"}
    uri = "sudoku://" + base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    item = {
        "port": 18553,
        "uri": uri,
        "config": json.dumps({"server_address": "192.0.2.22:18553",
                              "key": "test-key", "mode": "client"}),
    }
    result = binding._rewrite_modern_item(item, "sudoku", "192.0.2.23", 50022)
    assert result["port"] == 50022
    config = json.loads(result["config"])
    assert config["server_address"] == "192.0.2.23:50022"
    assert config["key"] == "test-key"
    p = result["uri"][len("sudoku://"):]
    actual = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    assert actual["p"] == 50022
    assert actual["h"] == "192.0.2.23"
    assert actual["k"] == "test-key"


def test_public_port_reservation_never_overlaps_legacy_pools():
    assert binding._shared_sudoku_public_port(1) == 50001
    assert binding._shared_sudoku_public_port(999) == 50999
    try:
        binding._shared_sudoku_public_port(1000)
    except RuntimeError:
        pass
    else:
        raise AssertionError("out-of-range exit accepted")
    assert not set(range(50001, 51000)).intersection(range(40000, 50000))


def main():
    for check in (
        test_central_shared_exit_has_one_route_for_all_users,
        test_public_shared_endpoint_matches_its_tunnel_route,
        test_retired_legacy_exit_generates_no_sudoku_routes,
        test_shared_rewrite_preserves_private_key,
        test_public_port_reservation_never_overlaps_legacy_pools,
    ):
        check()
    print("SUDOKU_SHARED_TUNNEL_V2_SMOKE_OK")


if __name__ == "__main__":
    main()
