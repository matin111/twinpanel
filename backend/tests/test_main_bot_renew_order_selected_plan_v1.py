"""No-money-write contract tests for picking a different renewal plan."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.models import Plan
from app.renewal_models import SubscriptionRenewalOrder
from app.store_models import StoreOrder
from app.routers import customer_subscription_management as mod


def mock_plan(plan_id=8, name="جدید", price=150000):
    return SimpleNamespace(
        id=plan_id, name=name, is_active=True, price_toman=price,
        traffic_gb=45, duration_days=60,
    )


class Query:
    def __init__(self, result=None):
        self.result = result

    def filter(self, *_args):
        return self

    def first(self):
        return self.result


class FakeDb:
    def __init__(self, plan, existing=None):
        self.plan, self.existing = plan, existing
        self.added = []
        self.commits = 0

    def get(self, model, plan_id):
        if model is Plan and plan_id == self.plan.id:
            return self.plan
        return None

    def query(self, model):
        return Query(self.existing if model is StoreOrder else None)

    def add(self, record):
        self.added.append(record)
        if isinstance(record, StoreOrder) and record.id is None:
            record.id = 812

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def refresh(self, _record):
        pass

    def rollback(self):
        pass


class MainRenewOrderTests(unittest.TestCase):
    def setUp(self):
        self.sub = SimpleNamespace(id=39, user_id=77, plan_id=3, status="active")
        self.user = SimpleNamespace(id=77)

    def call(self, db, plan_id, key="unique-key"):
        with (
            patch.object(mod, "_owned_subscription", return_value=self.sub),
            patch.object(mod, "_protocols", return_value=["openvpn"]),
            patch.object(mod, "_order_out", side_effect=lambda row: {
                "id": row.id,
                "amount_toman": row.amount_toman,
            }),
        ):
            return mod.create_renewal_order(
                subscription_id=39,
                payload=mod.RenewOrderIn(plan_id=plan_id, idempotency_key=key),
                user=self.user, db=db,
            )

    def test_new_plan_billed_without_replacing_account(self):
        db = FakeDb(mock_plan())
        result = self.call(db, plan_id=8)
        self.assertEqual(result["amount_toman"], 150000)
        self.assertTrue(result["renewal"])
        self.assertEqual(result["renew_subscription_id"], 39)
        self.assertEqual(self.sub.plan_id, 3)
        order = next(r for r in db.added if isinstance(r, StoreOrder))
        renewal = next(r for r in db.added if isinstance(r, SubscriptionRenewalOrder))
        self.assertEqual(order.plan_id, 8)
        self.assertEqual(renewal.plan_id, 8)
        self.assertEqual(renewal.subscription_id, 39)
        self.assertEqual(renewal.user_id, 77)
        self.assertEqual(db.commits, 1)

    def test_private_reseller_plan_rejected_before_money_write(self):
        db = FakeDb(mock_plan(name="__tp_reseller__not-public"))
        with self.assertRaises(HTTPException) as caught:
            self.call(db, 8)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(db.added, [])

    def test_unpriced_plan_rejected(self):
        db = FakeDb(mock_plan(price=0))
        with self.assertRaises(HTTPException) as caught:
            self.call(db, 8)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(db.added, [])

    def test_reused_order_key_for_different_plan_rejected(self):
        db = FakeDb(mock_plan(), existing=SimpleNamespace(id=999, user_id=77))
        with self.assertRaises(HTTPException) as caught:
            self.call(db, 8, key="already-used-for-another-order")
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(db.added, [])

    def test_plan_id_validation(self):
        with self.assertRaises(ValidationError):
            mod.RenewOrderIn(plan_id=0)
        self.assertIsNone(mod.RenewOrderIn().plan_id)


if __name__ == "__main__":
    unittest.main()
