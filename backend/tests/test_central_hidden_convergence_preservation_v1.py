"""Regression: legacy convergence must not erase centrally staged hidden items."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

from app.models import NodeStatus, NodeType
from app import node_subscription_convergence_v114 as convergence
from app.services import central_runtime_ownership_v1


def _db(*, hidden=True, retired=False, status=NodeStatus.ONLINE):
    node = SimpleNamespace(
        id=14, retired_at=object() if retired else None,
        node_type=NodeType.EXIT, status=status, show_to_users=not hidden,
    )
    db = MagicMock()
    db.info = {}
    db.get.return_value = node
    db.query.return_value.filter.return_value.first.return_value = (
        SimpleNamespace(status="online")
    )
    return db


class HiddenCentralItemPreservationTests(unittest.TestCase):
    def _item(self):
        return {"node_id": 14, "config": "opaque-test-delivery"}

    def _ad(self, *, customer_usable=False):
        ad = MagicMock()
        ad._autosync_item_node_id.return_value = 14
        ad._delivery_item_is_usable.return_value = customer_usable
        return ad

    def test_hidden_centrally_owned_item_survives_legacy_reconcile(self):
        ad = self._ad(customer_usable=False)
        with patch.object(central_runtime_ownership_v1, "is_central_node",
                          return_value=True):
            self.assertTrue(convergence._modern_item_is_usable(
                ad, _db(hidden=True), "hysteria2", self._item()
            ))
        ad._delivery_item_is_usable.assert_not_called()

    def test_central_ownership_is_read_only_once_per_session(self):
        db = _db(hidden=True)
        ad = self._ad(customer_usable=False)
        with patch.object(central_runtime_ownership_v1, "is_central_node",
                          return_value=True) as lookup:
            for protocol in ("anytls", "hysteria2", "naive", "tuic"):
                self.assertTrue(convergence._modern_item_is_usable(
                    ad, db, protocol, self._item()
                ))
            lookup.assert_called_once_with(db, 14)
        ad._delivery_item_is_usable.assert_not_called()

    def test_unregistered_hidden_node_is_not_implicitly_trusted(self):
        ad = self._ad()
        with patch.object(central_runtime_ownership_v1, "is_central_node",
                          return_value=False):
            self.assertFalse(convergence._modern_item_is_usable(
                ad, _db(hidden=True), "hysteria2", self._item()
            ))

    def test_published_node_still_requires_customer_delivery_guard(self):
        ad = self._ad(customer_usable=False)
        with patch.object(central_runtime_ownership_v1, "is_central_node") as owner:
            self.assertFalse(convergence._modern_item_is_usable(
                ad, _db(hidden=False), "hysteria2", self._item()
            ))
            owner.assert_not_called()
        ad._delivery_item_is_usable.assert_called_once()

    def test_retired_node_is_never_preserved(self):
        ad = self._ad()
        with patch.object(central_runtime_ownership_v1, "is_central_node") as owner:
            self.assertFalse(convergence._modern_item_is_usable(
                ad, _db(hidden=True, retired=True), "hysteria2", self._item()
            ))
            owner.assert_not_called()

    def test_hidden_central_item_missing_runtime_config_is_not_ready(self):
        db = _db(hidden=True)
        db.query.return_value.filter.return_value.first.return_value = None
        with patch.object(central_runtime_ownership_v1, "is_central_node",
                          return_value=True):
            self.assertFalse(convergence._modern_item_is_usable(
                self._ad(), db, "hysteria2", self._item()
            ))


if __name__ == "__main__":
    unittest.main()
