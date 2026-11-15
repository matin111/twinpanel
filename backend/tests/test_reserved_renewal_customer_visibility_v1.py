"""Read-only visibility regression for reserved renewals across customer channels."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

from app.subscription_renewal_status_v1 import next_reserved_renewal


class ReservedRenewalVisibilityTest(unittest.TestCase):
    def test_queued_next_period_has_public_fields_only(self):
        row = SimpleNamespace(
            status="queued", plan_id=5, plan_name="ویژه",
            traffic_bytes=25 * 1024**3, duration_days=30,
            created_at=datetime(2026, 11, 15, 5, 15, 0),
            source="website_bot", source_reference="secret-order",
            actor="admin:123", amount_toman=150000,
        )
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = row
        result = next_reserved_renewal(db, 42)
        self.assertEqual(result["status"], "reserved")
        self.assertEqual(result["traffic_gb"], 25)
        self.assertEqual(result["duration_days"], 30)
        self.assertTrue(result["reserved_at"].endswith("Z"))
        self.assertEqual(result["activation"], "when_current_quota_or_expiry_ends")
        self.assertNotIn("source_reference", result)
        self.assertNotIn("actor", result)
        self.assertNotIn("amount_toman", result)
        self.assertNotIn("secret-order", str(result))

    def test_blocked_paid_renewal_warns_without_changing_period(self):
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(
            status="blocked", plan_id=5, plan_name="ویتوری",
            traffic_bytes=10 * 1024**3, duration_days=30,
            created_at=datetime(2026, 11, 15, 5, 15, 0),
        )
        result = next_reserved_renewal(db, 42)
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("بررسی", result["message"])

    def test_no_reserved_period_has_no_false_badge(self):
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        self.assertIsNone(next_reserved_renewal(db, 42))

    def test_projection_does_not_mutate_database(self):
        db = Mock()
        db.execute.return_value.scalar_one_or_none.return_value = None
        next_reserved_renewal(db, 42)
        db.add.assert_not_called()
        db.commit.assert_not_called()
        db.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
