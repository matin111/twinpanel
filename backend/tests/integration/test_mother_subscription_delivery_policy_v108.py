import asyncio
from types import SimpleNamespace

from app.models import Node, NodeProtocolConfig, NodeType
from app import mother_subscription_delivery_policy_v108 as policy


class _Query:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._row


class _DB:
    def __init__(self, *, reseller_row=None, nodes=None, protocol_config=None):
        self.reseller_row = reseller_row
        self.nodes = nodes or {}
        self.protocol_config = protocol_config

    def query(self, *args, **kwargs):
        if args and args[0] is NodeProtocolConfig:
            return _Query(self.protocol_config)
        return _Query(self.reseller_row)

    def get(self, model, key):
        if model is Node:
            return self.nodes.get(int(key))
        return None


def _node(node_id: int, *, mother: bool):
    return SimpleNamespace(
        id=node_id,
        is_mother=mother,
        agent_url="local://core" if mother else "https://agent.example.invalid",
    )


def _runtime_node(node_id: int, *, mother: bool = False):
    return SimpleNamespace(
        id=node_id,
        is_mother=mother,
        agent_url="local://core" if mother else "https://agent.example.invalid",
        retired_at=None,
        show_to_users=True,
        status="online",
        node_type=NodeType.EXIT,
    )


def test_direct_subscription_uses_admin_policy():
    db = _DB(reseller_row=None)
    sub = SimpleNamespace(id=10)

    original_admin = policy.admin_can_use_mother
    original_reseller = policy.reseller_can_use_mother

    try:
        policy.admin_can_use_mother = lambda _db: False
        policy.reseller_can_use_mother = lambda _db, _id: True
        assert policy._subscription_can_use_mother(db, sub) is False

        policy.admin_can_use_mother = lambda _db: True
        assert policy._subscription_can_use_mother(db, sub) is True
    finally:
        policy.admin_can_use_mother = original_admin
        policy.reseller_can_use_mother = original_reseller


def test_reseller_subscription_uses_reseller_policy():
    db = _DB(reseller_row=(77,))
    sub = SimpleNamespace(id=11)

    original_admin = policy.admin_can_use_mother
    original_reseller = policy.reseller_can_use_mother

    try:
        policy.admin_can_use_mother = lambda _db: True
        policy.reseller_can_use_mother = (
            lambda _db, reseller_id: reseller_id == 77
        )
        assert policy._subscription_can_use_mother(db, sub) is True

        policy.reseller_can_use_mother = lambda _db, _id: False
        assert policy._subscription_can_use_mother(db, sub) is False
    finally:
        policy.admin_can_use_mother = original_admin
        policy.reseller_can_use_mother = original_reseller


def test_multilink_filter_removes_mother_without_mutating_stored_payload():
    db = _DB(
        nodes={
            1: _node(1, mother=True),
            5: _node(5, mother=False),
        }
    )

    payload = {
        "subscription_id": 12,
        "credentials": [
            {
                "protocol": "cisco",
                "items": [
                    {"node_id": 1, "node": "TwinPanel Local Core"},
                    {"node_id": 5, "node": "usa"},
                ],
            },
            {
                "protocol": "openvpn",
                "items": {
                    "node_id": 1,
                    "node": "TwinPanel Local Core",
                },
            },
        ],
    }

    result = policy._filter_mother_from_delivery(db, payload)

    assert len(result["credentials"]) == 1
    assert result["credentials"][0]["protocol"] == "cisco"
    assert result["credentials"][0]["items"] == [
        {"node_id": 5, "node": "usa"}
    ]

    # Stored/single-server payload remains intact. Only the Multi-Link copy is
    # filtered, so Mother can still appear as an individual server.
    assert len(payload["credentials"]) == 2
    assert len(payload["credentials"][0]["items"]) == 2


def test_stored_info_preserves_mother_when_multilink_policy_is_disabled():
    db = _DB(
        nodes={
            1: _node(1, mother=True),
            5: _node(5, mother=False),
        }
    )
    sub = SimpleNamespace(id=13)
    payload = {
        "subscription_id": 13,
        "credentials": [
            {
                "protocol": "cisco",
                "items": [
                    {"node_id": 1},
                    {"node_id": 5},
                ],
            }
        ],
    }

    original_info = policy._original_stored_info
    original_allowed = policy._subscription_can_use_mother

    try:
        policy._original_stored_info = lambda _db, _sub: payload
        policy._subscription_can_use_mother = lambda _db, _sub: False

        visible = policy._stored_info_with_mother_policy(db, sub)
        assert visible is payload
        assert visible["credentials"][0]["items"] == [
            {"node_id": 1},
            {"node_id": 5},
        ]
    finally:
        policy._original_stored_info = original_info
        policy._subscription_can_use_mother = original_allowed


def test_mother_account_delivery_uses_local_runtime_executor():
    mother = _runtime_node(1, mother=True)
    remote = _runtime_node(5, mother=False)
    db = _DB(nodes={1: mother, 5: remote})
    calls = []

    original_local = policy.connect_protocol_runtime
    original_remote = policy._original_ssh_connect_saved

    async def local_connect(node, _db):
        calls.append(("local", int(node.id)))
        return "LOCAL"

    async def remote_connect(node, _db):
        calls.append(("remote", int(node.id)))
        return "REMOTE"

    async def run():
        policy.connect_protocol_runtime = local_connect
        policy._original_ssh_connect_saved = remote_connect
        try:
            assert await policy._runtime_aware_connect_saved(mother, db) == "LOCAL"
            assert await policy._runtime_aware_connect_saved(remote, db) == "REMOTE"
        finally:
            policy.connect_protocol_runtime = original_local
            policy._original_ssh_connect_saved = original_remote

    asyncio.run(run())
    assert calls == [("local", 1), ("remote", 5)]


def test_modern_direct_exit_without_tunnel_is_usable_when_runtime_online():
    exit_node = _runtime_node(5)
    db = _DB(
        nodes={5: exit_node},
        protocol_config=SimpleNamespace(status="online"),
    )

    original_usable = policy._original_delivery_item_is_usable
    original_tunnels = policy.account_delivery._delivery_active_tunnels
    try:
        policy._original_delivery_item_is_usable = lambda _db, _protocol, _item: False
        policy.account_delivery._delivery_active_tunnels = lambda _db, _node: []
        assert policy._modern_direct_item_is_usable(
            db,
            "anytls",
            {"node_id": 5},
        ) is True

        db.protocol_config = SimpleNamespace(status="offline")
        assert policy._modern_direct_item_is_usable(
            db,
            "anytls",
            {"node_id": 5},
        ) is False
    finally:
        policy._original_delivery_item_is_usable = original_usable
        policy.account_delivery._delivery_active_tunnels = original_tunnels


if __name__ == "__main__":
    test_direct_subscription_uses_admin_policy()
    test_reseller_subscription_uses_reseller_policy()
    test_multilink_filter_removes_mother_without_mutating_stored_payload()
    test_stored_info_preserves_mother_when_multilink_policy_is_disabled()
    test_mother_account_delivery_uses_local_runtime_executor()
    test_modern_direct_exit_without_tunnel_is_usable_when_runtime_online()
    print("MOTHER_SUBSCRIPTION_DELIVERY_POLICY_V110_OK")
