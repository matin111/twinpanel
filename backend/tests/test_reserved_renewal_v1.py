"""Focused tests for reserved renewal activation.

Run: PYTHONPATH=backend python -m unittest backend.tests.test_reserved_renewal_v1
No network or database connection is used.
"""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.models import SubscriptionStatus
from app import reserved_renewal_service as service


class Result:
    def __init__(self, value=None, items=None):
        self.value, self.items = value, items

    def scalars(self):
        return self

    def all(self):
        return self.items or []

    def scalar_one_or_none(self):
        return self.value


class FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.commits = 0
        self.rollbacks = 0

    def execute(self, _query):
        return self.results.pop(0)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class DeferredRenewalTest(unittest.TestCase):
    def subscription(self, **overrides):
        values = dict(id=22, plan_id=5, status=SubscriptionStatus.ACTIVE,
                      traffic_limit_bytes=10 * 1024**3,
                      traffic_used_bytes=4 * 1024**3,
                      expires_at=datetime.utcnow() + timedelta(days=5),
                      starts_at=datetime.utcnow() - timedelta(days=25),
                      account_username="untouched", account_password_encrypted="encrypted",
                      activation_duration_days=30)
        values.update(overrides)
        return SimpleNamespace(**values)

    def pending(self):
        return SimpleNamespace(id=80, subscription_id=22, plan_id=5,
                               traffic_bytes=25 * 1024**3, duration_days=30,
                               source="website_bot", actor="customer:1",
                               status="queued", activated_at=None)

    def test_not_due_does_not_modify_running_period(self):
        sub = self.subscription()
        original_expiry = sub.expires_at
        db = FakeDB([Result(items=[22]), Result(value=sub)])
        self.assertEqual(service.activate_due_renewals(db), 0)
        self.assertEqual(sub.traffic_used_bytes, 4 * 1024**3)
        self.assertEqual(sub.expires_at, original_expiry)
        self.assertEqual(db.commits, 0)

    def test_quota_exhaustion_activates_one_queued_cycle(self):
        sub = self.subscription(traffic_used_bytes=10 * 1024**3)
        pending = self.pending()
        db = FakeDB([Result(items=[22]), Result(value=sub), Result(value=pending)])
        events = []
        with patch.object(service, "reset_subscription_period_usage",
                          side_effect=lambda db, sub, **kw: setattr(sub, "traffic_used_bytes", 0)), \
             patch.object(service, "queue_subscription_enforcement") as enforce, \
             patch.object(service, "history", side_effect=lambda *a: events.append(a)):
            self.assertEqual(service.activate_due_renewals(db), 1)
            enforce.assert_called_once()
        self.assertEqual(sub.traffic_used_bytes, 0)
        self.assertEqual(sub.traffic_limit_bytes, 25 * 1024**3)
        self.assertEqual(sub.account_username, "untouched")
        self.assertEqual(sub.account_password_encrypted, "encrypted")
        self.assertEqual(pending.status, "activated")
        self.assertEqual(db.commits, 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][2], "renewal_activated")

    def test_expiry_triggers_even_without_quota_exhaustion(self):
        sub = self.subscription(status=SubscriptionStatus.EXPIRED,
                                expires_at=datetime.utcnow() - timedelta(seconds=1))
        pending = self.pending()
        db = FakeDB([Result(items=[22]), Result(value=sub), Result(value=pending)])
        with patch.object(service, "reset_subscription_period_usage"), \
             patch.object(service, "queue_subscription_enforcement"), \
             patch.object(service, "history"):
            self.assertEqual(service.activate_due_renewals(db), 1)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertGreater(sub.expires_at, datetime.utcnow())

    def test_manual_suspension_is_not_lifted(self):
        sub = self.subscription(status=SubscriptionStatus.SUSPENDED,
                                expires_at=datetime.utcnow() - timedelta(seconds=1))
        pending = self.pending()
        db = FakeDB([Result(items=[22]), Result(value=sub), Result(value=pending)])
        with patch.object(service, "reset_subscription_period_usage"), \
             patch.object(service, "queue_subscription_enforcement") as enforce, \
             patch.object(service, "history"):
            self.assertEqual(service.activate_due_renewals(db), 1)
            enforce.assert_not_called()
        self.assertEqual(sub.status, SubscriptionStatus.SUSPENDED)

if __name__ == "__main__":
    unittest.main()
