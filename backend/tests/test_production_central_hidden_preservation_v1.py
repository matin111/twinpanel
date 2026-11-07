"""Production-compatible guard for hidden centrally owned Exit credentials."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

from app.models import NodeStatus, NodeType
from app import node_subscription_convergence_v114 as convergence
from app.services import central_runtime_ownership_v1 as central_owner


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


class ProductionCentralHiddenPreservationTests(unittest.TestCase):
    def _ad(self, customer_usable=False):
        ad = MagicMock()
        ad._autosync_item_node_id.return_value = 14
        ad._delivery_item_is_usable.return_value = customer_usable
        return ad

    def _item(self):
        return {"node_id": 14, "config": "opaque-test-delivery"}

    def test_hidden_central_delivery_preserved_without_customer_visibility(self):
        ad = self._ad(customer_usable=False)
        with patch.object(central_owner, "get_value", return_value="v1"):
            self.assertTrue(convergence._modern_item_is_usable(
                ad, _db(hidden=True), "hysteria2", self._item()
            ))
        ad._delivery_item_is_usable.assert_not_called()

    def test_unregistered_hidden_node_rejected(self):
        with patch.object(central_owner, "get_value", return_value=""):
            self.assertFalse(convergence._modern_item_is_usable(
                self._ad(), _db(hidden=True), "hysteria2", self._item()
            ))

    def test_published_node_requires_delivery_guard(self):
        ad = self._ad(customer_usable=False)
        with patch.object(central_owner, "get_value") as lookup:
            self.assertFalse(convergence._modern_item_is_usable(
                ad, _db(hidden=False), "hysteria2", self._item()
            ))
            lookup.assert_not_called()
        ad._delivery_item_is_usable.assert_called_once()

    def test_retired_node_rejected(self):
        with patch.object(central_owner, "get_value") as lookup:
            self.assertFalse(convergence._modern_item_is_usable(
                self._ad(), _db(hidden=True, retired=True),
                "hysteria2", self._item()
            ))
            lookup.assert_not_called()

    def test_missing_node_runtime_config_rejected(self):
        db = _db(hidden=True)
        db.query.return_value.filter.return_value.first.return_value = None
        with patch.object(central_owner, "get_value", return_value="v1"):
            self.assertFalse(convergence._modern_item_is_usable(
                self._ad(), db, "hysteria2", self._item()
            ))

    def test_ownership_query_cached_once_for_multiple_protocols(self):
        db = _db(hidden=True)
        ad = self._ad()
        with patch.object(central_owner, "get_value",
                          return_value="v1") as lookup:
            for protocol in ("hysteria2", "anytls", "naive", "tuic"):
                self.assertTrue(convergence._modern_item_is_usable(
                    ad, db, protocol, self._item()
                ))
            lookup.assert_called_once_with(
                db, "vpn.central_runtime.exit.14", ""
            )


if __name__ == "__main__":
    unittest.main()
