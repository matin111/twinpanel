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


def test_account_creation_fences_legacy_when_shared_node_exists():
    old = node()
    old.id = 6
    shared = node()
    shared.id = 19
    db = FakeDB({6: old, 19: shared})
    with patch.object(delivery, "is_central_node", side_effect=lambda db, nid: nid == 19):
        assert delivery.has_published_central_sudoku_owner(db, [old, shared])
        assert not delivery.has_published_central_sudoku_owner(db, [old])
        assert delivery.ready_central_sudoku_items(db, [
            {"node_id": 6, "port": 30001},
            {"node_id": 19, "port": 18553},
        ]) == [{"node_id": 19, "port": 18553}]


def test_unpublished_central_owner_cannot_fence_account_creation():
    shared = node(visible=False)
    shared.id = 19
    db = FakeDB({19: shared})
    with patch.object(delivery, "is_central_node", return_value=True):
        assert not delivery.has_published_central_sudoku_owner(db, [shared])


def test_account_provisioning_guards_before_legacy_driver():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "app/routers/modern_account_delivery_v1.py"
    code = path.read_text(encoding="utf-8")
    assert 'if protocol == "sudoku" and central_sudoku_owner:' in code
    assert code.index('if protocol == "sudoku" and central_sudoku_owner:') < code.index(
        'items, protocol_errors = await _provision_modern_protocol('
    )
    assert '"pending_protocols": pending_protocols' in code
    assert 'if not results and not pending_protocols:' in code


def test_pending_sudoku_never_triggers_paid_subscription_suspension():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app"
    worker = (root / "services/fast_provision_worker_v1.py").read_text(encoding="utf-8")
    create = (root / "routers/subscription_create_fast_v1.py").read_text(encoding="utf-8")
    store = (root / "routers/store.py").read_text(encoding="utf-8")
    modern = (root / "routers/modern_account_delivery_v1.py").read_text(encoding="utf-8")
    assert '"sudoku" in (result.get("pending_protocols") or ())' in worker
    assert 'return "retry", "central_sudoku_reconciliation_pending"' in worker
    assert worker.index('return "retry", "central_sudoku_reconciliation_pending"') < worker.index(
        'if reason == "provisioning_conflict"'
    )
    assert 'if "sudoku" in (provisioning.get("pending_protocols") or ()):' in create
    assert create.index('TWINPANEL_SUDOKU_CENTRAL_CONVERGENCE_PENDING') < create.index(
        'if _should_suspend_after_background_provisioning('
    )
    assert 'if "sudoku" in (provision_result.get("pending_protocols") or ()):' in store
    assert store.index('central_reconciliation_pending": True') < store.index(
        'if not _delivery_ready_for_order('
    )
    assert '"central_reconciliation_pending": bool(pending_protocols)' in modern
    assert 'central_sudoku_order = has_published_central_sudoku_owner(' in store
    assert 'or central_sudoku_order):' in store
    assert store.index('central_sudoku_order = has_published_central_sudoku_owner(') < store.index(
        'provision_result = await provision_account(int(order.subscription_id), db)'
    )


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("SUDOKU_CENTRAL_DELIVERY_V1_SMOKE_OK")
