"""Contract tests for admin custom/plan reserved renewals.

Run: PYTHONPATH=backend python -m unittest backend.tests.test_admin_manual_renewal_modes_v1
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.models import Plan, Subscription
from app.routers import reserved_renewal_v1 as router


class FakeDB:
    def __init__(self):
        self.sub = SimpleNamespace(id=3594, plan_id=38)
        self.plans = {
            38: SimpleNamespace(id=38, name="180 گیگ", traffic_gb=180,
                                duration_days=60, is_active=True),
            9: SimpleNamespace(id=9, name="10 گیگ", traffic_gb=10,
                               duration_days=30, is_active=True),
        }
        self.commits = 0

    def get(self, model, id_):
        return self.sub if model is Subscription else self.plans.get(id_) if model is Plan else None

    def commit(self):
        self.commits += 1


class AdminRenewalModeTest(unittest.TestCase):
    def reserve(self, payload):
        db = FakeDB()
        admin = SimpleNamespace(id=1)
        with patch.object(router, "reserve_renewal", return_value=SimpleNamespace(id=4, status="queued")) as reserve:
            result = router.reserve_admin(3594, payload, db=db, admin=admin)
            self.assertEqual(result["status"], "queued")
            self.assertEqual(db.commits, 1)
            return reserve.call_args.kwargs

    def test_custom_renewal_not_labeled_as_old_plan(self):
        args = self.reserve(router.ReserveRequest(
            mode="custom", traffic_gb=10, duration_days=30))
        self.assertIsNone(args["plan_id"])
        self.assertIn("10 گیگ", args["plan_name"])
        self.assertEqual(args["traffic_bytes"], 10 * 1024**3)
        self.assertEqual(args["duration_days"], 30)

    def test_selected_plan_controls_quota_duration(self):
        args = self.reserve(router.ReserveRequest(
            mode="plan", plan_id=9, traffic_gb=999, duration_days=99))
        self.assertEqual(args["plan_id"], 9)
        self.assertEqual(args["plan_name"], "10 گیگ")
        self.assertEqual(args["traffic_bytes"], 10 * 1024**3)
        self.assertEqual(args["duration_days"], 30)

    def test_legacy_request_keeps_existing_behavior(self):
        args = self.reserve(router.ReserveRequest(
            traffic_gb=10, duration_days=30, plan_id=38))
        self.assertEqual(args["plan_id"], 38)
        self.assertEqual(args["plan_name"], "180 گیگ")


if __name__ == "__main__":
    unittest.main()
