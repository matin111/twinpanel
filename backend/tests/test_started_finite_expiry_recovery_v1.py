"""Regression coverage: started finite subscriptions must have an expiry."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest

from app.models import Plan
from app.subscription_override_models import (
    SubscriptionRuntimeOverride,
    duration_is_unlimited,
    effective_expiry_at,
)
from app.quota_service import _activate_from_accepted_traffic
from app.routers.public_connection_hub_v5 import _expiry_with_days


START = datetime(2026, 11, 9, 22, 23, 14)


class FakeDb:
    def __init__(self, *, plan_days=60, unlimited=False):
        self.plan = SimpleNamespace(duration_days=plan_days)
        self.override = SimpleNamespace(duration_unlimited=unlimited)

    def get(self, model, _key):
        if model is Plan:
            return self.plan
        if model is SubscriptionRuntimeOverride:
            return self.override
        raise AssertionError(f"Unexpected model {model}")


def sub(*, started=START, expiry=None, stored_days=0):
    return SimpleNamespace(
        id=3594, plan_id=38, starts_at=started, expires_at=expiry,
        activation_duration_days=stored_days,
    )


class StartedFiniteExpiryTests(unittest.TestCase):
    def test_started_plan_has_real_expiry_even_when_snapshot_zero(self):
        db, account = FakeDb(), sub()
        expiry = effective_expiry_at(db, account)
        self.assertEqual(expiry, START + timedelta(days=60))
        self.assertIsNone(account.expires_at)  # display lookup is read only
        display, remaining = _expiry_with_days(db, account, START + timedelta(days=2))
        self.assertEqual(display, "2027/01/08")
        self.assertIn("58 روز", remaining)

    def test_first_use_not_started_still_waits(self):
        db, account = FakeDb(), sub(started=None)
        self.assertIsNone(effective_expiry_at(db, account))
        display, _ = _expiry_with_days(db, account, START)
        self.assertEqual(display, "پس از اولین اتصال")

    def test_unlimited_never_gets_expiry(self):
        db, account = FakeDb(unlimited=True), sub()
        self.assertTrue(duration_is_unlimited(db, account))
        self.assertIsNone(effective_expiry_at(db, account))
        self.assertFalse(_activate_from_accepted_traffic(db, account, accepted=100, now=START))
        self.assertIsNone(account.expires_at)

    def test_explicit_expiry_is_authoritative(self):
        db = FakeDb()
        original = START + timedelta(days=12)
        self.assertEqual(effective_expiry_at(db, sub(expiry=original)), original)

    def test_accepted_traffic_repairs_missing_expiry_once(self):
        db, account = FakeDb(), sub()
        self.assertFalse(_activate_from_accepted_traffic(db, account, accepted=0, now=START + timedelta(days=2)))
        self.assertIsNone(account.expires_at)
        self.assertTrue(_activate_from_accepted_traffic(db, account, accepted=128, now=START + timedelta(days=2)))
        self.assertEqual(account.starts_at, START)
        self.assertEqual(account.activation_duration_days, 60)
        self.assertEqual(account.expires_at, START + timedelta(days=60))
        self.assertFalse(_activate_from_accepted_traffic(db, account, accepted=128, now=START + timedelta(days=3)))
        self.assertEqual(account.expires_at, START + timedelta(days=60))

    def test_first_use_still_activates_from_accepted_usage(self):
        db, account = FakeDb(), sub(started=None)
        moment = START + timedelta(days=1)
        self.assertTrue(_activate_from_accepted_traffic(db, account, accepted=128, now=moment))
        self.assertEqual(account.starts_at, moment)
        self.assertEqual(account.expires_at, moment + timedelta(days=60))
        self.assertEqual(account.activation_duration_days, 60)


if __name__ == "__main__":
    unittest.main()
