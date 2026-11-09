"""Sudoku central-delivery preference and unchanged legacy fallback."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.models import NodeType
from app.services import sudoku_central_delivery_v1 as delivery


class FakeDB:
    def __init__(self, nodes):
        self.nodes = nodes
        self.seen = []

    def get(self, model, node_id):
        self.seen.append(int(node_id))
        return self.nodes.get(int(node_id))


def node(*, online=True, retired=False, visible=True):
    return SimpleNamespace(
        node_type=NodeType.EXIT,
        show_to_users=visible,
        retired_at="2026-01-01" if retired else None,
        status="online" if online else "offline",
    )


def test_central_preference_keeps_two_shared_nodes_only():
    legacy_a = {"node_id": 6, "port": 30000, "uri": "do-not-modify"}
    shared_a = {"node_id": 19, "port": 18553, "uri": "shared-19"}
    legacy_b = {"node_id": 11, "port": 30001, "uri": "old-11"}
    shared_b = {"node_id": 22, "port": 18553, "uri": "shared-22"}
    itemlist = [legacy_a, shared_a, legacy_b, shared_b]
    db = FakeDB({6: node(), 11: node(), 19: node(), 22: node()})
    with patch.object(delivery, "is_central_node", side_effect=lambda db, nid: nid in {19, 22}):
        selected = delivery.prefer_central_sudoku_items(db, itemlist)
    assert selected == [shared_a, shared_b]
    assert itemlist == [legacy_a, shared_a, legacy_b, shared_b]
    assert selected[0] is shared_a
    assert selected[1] is shared_b


def test_missing_central_items_preserves_legacy():
    legacy = {"node_id": 6, "port": 30000, "uri": "old"}
    db = FakeDB({6: node()})
    with patch.object(delivery, "is_central_node", return_value=False):
        assert delivery.prefer_central_sudoku_items(db, [legacy]) == [legacy]


def test_unregistered_or_offline_node_is_not_preferred():
    old = {"node_id": 6, "port": 30000}
    offline = {"node_id": 19, "port": 18553}
    retired = {"node_id": 22, "port": 18553}
    db = FakeDB({6: node(), 19: node(online=False), 22: node(retired=True)})
    with patch.object(delivery, "is_central_node", return_value=True):
        assert delivery.prefer_central_sudoku_items(db, [old, offline, retired]) == [old, offline, retired]


def test_malformed_items_never_trigger_network_or_crypto_mutation():
    data = [None, [], {"node_id": "bad", "port": 18553}, {"node_id": 19, "port": 0}]
    db = FakeDB({19: node()})
    with patch.object(delivery, "is_central_node", return_value=True):
        assert delivery.prefer_central_sudoku_items(db, data) is data
    assert db.seen == []


def test_unpublished_central_node_not_preferred():
    db = FakeDB({19: node(visible=False)})
    with patch.object(delivery, "is_central_node", return_value=True):
        items = [{"node_id": 19, "port": 18553}]
        assert delivery.prefer_central_sudoku_items(db, items) is items


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("SUDOKU_CENTRAL_DELIVERY_V1_SMOKE_OK")
