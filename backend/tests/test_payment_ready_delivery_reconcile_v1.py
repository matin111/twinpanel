"""Payment recovery must finalize only verified orders with complete delivery.

Run: PYTHONPATH=backend python -m unittest backend.tests.test_payment_ready_delivery_reconcile_v1
"""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import payment_fulfillment_fast_path as service
from app.routers import store


class ReadyDeliveryReconcileTest(unittest.TestCase):
    def scenario(self, *, verified=True, ready=True):
        now = datetime.utcnow()
        order = SimpleNamespace(
            id=360, status="provisioning", subscription_id=4040,
            payment_method="card_to_card",
            created_at=now - timedelta(minutes=20),
            paid_at=None,
        )
        intent = (SimpleNamespace(id=297, verified_at=now - timedelta(minutes=10))
                  if verified else None)
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [order]
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = intent
        db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = order
        # One canonical delivery check before locking, one after locking.
        with (
            patch.object(service, "SessionLocal", return_value=db),
            patch.object(store, "_existing_delivery_snapshot", return_value={"ok": ready}),
            patch.object(store, "_delivery_ready_for_order", return_value=ready),
            patch.object(store, "_mark_order_fulfilled") as finalize,
        ):
            result = service.reconcile_ready_payment_orders_once()
            return result, order, finalize

    def test_ready_verified_account_is_finalized(self):
        result, order, finalize = self.scenario()
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["order_ids"], [360])
        self.assertIsNotNone(order.paid_at)
        finalize.assert_called_once()

    def test_unverified_payment_is_not_finalized(self):
        result, _, finalize = self.scenario(verified=False)
        self.assertEqual(result["completed"], 0)
        finalize.assert_not_called()

    def test_missing_delivery_is_not_finalized(self):
        result, _, finalize = self.scenario(ready=False)
        self.assertEqual(result["completed"], 0)
        finalize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
