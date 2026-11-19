"""Plan-scoped central coupons remain restricted at creation and redemption."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.discount_models import DiscountCode
from app.discount_service import evaluate_discount
from app.routers import discounts


class FakeQuery:
    def __init__(self, plan_ids=()):
        self.plan_ids = plan_ids

    def filter(self, *_filters):
        return self

    def all(self):
        return [(item,) for item in self.plan_ids]

    def count(self):
        return 0


class FakeDb:
    def __init__(self, valid_plan_ids=()):
        self.valid_plan_ids = valid_plan_ids
        self.commits = 0
        self.queries = 0

    def query(self, _model):
        self.queries += 1
        return FakeQuery(self.valid_plan_ids)

    def commit(self):
        self.commits += 1

    def refresh(self, _row):
        pass


def coupon(owner_type="central"):
    return DiscountCode(
        id=100,
        owner_type=owner_type,
        owner_key=owner_type,
        reseller_id=None,
        code="OLD",
        discount_type="percent",
        discount_value=10,
        min_order_toman=0,
        applies_to="both",
        plan_ids=[],
        is_active=True,
    )


def payload(plan_ids):
    return discounts.DiscountIn(
        code="PLAN10",
        discount_type="percent",
        discount_value=10,
        plan_ids=plan_ids,
    )


class AdminDiscountPlanScopeTests(unittest.TestCase):
    def test_selected_central_plans_are_saved_without_duplicates(self):
        db = FakeDb(valid_plan_ids=[5, 9])
        row = coupon()
        result = discounts.save_discount(db, row=row, payload=payload([5, 9, 5]))
        self.assertEqual(result["plan_ids"], [5, 9])
        self.assertEqual(row.plan_ids, [5, 9])
        self.assertEqual(db.commits, 1)

    def test_reject_unknown_or_private_plans_before_writing(self):
        db = FakeDb(valid_plan_ids=[5])
        row = coupon()
        with self.assertRaises(HTTPException) as caught:
            discounts.save_discount(db, row=row, payload=payload([5, 999]))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(row.code, "OLD")
        self.assertEqual(db.commits, 0)

    def test_empty_plan_ids_keep_legacy_all_plans_scope(self):
        db = FakeDb()
        row = coupon()
        result = discounts.save_discount(db, row=row, payload=payload([]))
        self.assertEqual(result["plan_ids"], [])
        self.assertEqual(db.queries, 0)
        self.assertEqual(db.commits, 1)

    def test_reseller_scope_stays_compatible(self):
        db = FakeDb()
        row = coupon("reseller")
        result = discounts.save_discount(db, row=row, payload=payload([51]))
        self.assertEqual(result["plan_ids"], [51])
        self.assertEqual(db.queries, 0)

    def test_unselected_plan_cannot_redeem_coupon(self):
        db = FakeDb()
        row = coupon()
        row.plan_ids = [5, 9]
        with patch("app.discount_service._find_discount", return_value=row):
            with self.assertRaises(HTTPException) as caught:
                evaluate_discount(db, owner_type="central", reseller_id=None,
                                  user_id=12, code="PLAN10", plan_id=6,
                                  base_amount_toman=100000)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(db.queries, 0)

    def test_selected_plan_receives_discount(self):
        db = FakeDb()
        row = coupon()
        row.plan_ids = [5, 9]
        with patch("app.discount_service._find_discount", return_value=row):
            result = evaluate_discount(db, owner_type="central", reseller_id=None,
                                       user_id=12, code="PLAN10", plan_id=9,
                                       base_amount_toman=100000)
        self.assertEqual(result["discount_amount_toman"], 10000)
        self.assertEqual(result["final_amount_toman"], 90000)

    def test_zero_plan_id_is_rejected(self):
        with self.assertRaises(ValidationError):
            payload([0])


if __name__ == "__main__":
    unittest.main()
