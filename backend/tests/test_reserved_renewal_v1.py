"""Focused tests for reserved renewal activation.

Run: PYTHONPATH=backend python -m unittest backend.tests.test_reserved_renewal_v1
No network or database connection is used.
"""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app.models import SubscriptionStatus, Plan
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

    def scalar_one(self):
        if self.value is None:
            raise ValueError("No result")
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


class ReservationDB(FakeDB):
    def __init__(self, subscription, plan=None):
        super().__init__([Result(value=subscription), Result(value=None)])
        self.subscription = subscription
        self.plan = plan
        self.added = []

    def get(self, model, ident):
        return self.plan if model is Plan else None

    def add(self, record):
        self.added.append(record)

    def flush(self):
        for record in self.added:
            if hasattr(record, "source_reference") and record.id is None:
                record.id = 901


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

    def test_different_plan_is_queued_without_changing_running_account(self):
        sub = self.subscription()
        old_expiry = sub.expires_at
        db = ReservationDB(sub, SimpleNamespace(is_active=True, duration_days=45))
        row = service.reserve_renewal(
            db, subscription_id=22, plan_id=10, plan_name="new premium",
            traffic_bytes=40 * 1024**3, duration_days=45,
            source="website_bot", reference="order-222", actor="customer:1")
        self.assertEqual(row.plan_id, 10)
        self.assertEqual(row.status, "queued")
        self.assertEqual(sub.plan_id, 5)
        self.assertEqual(sub.expires_at, old_expiry)
        self.assertEqual(sub.traffic_used_bytes, 4 * 1024**3)
        self.assertEqual(sub.account_username, "untouched")

    def test_different_plan_is_not_provisioned_before_expiry(self):
        sub = self.subscription()
        db = FakeDB([Result(items=[] )])
        with patch.object(service, "provision_reserved_plan_at_cutover") as provision:
            self.assertEqual(service.activate_due_renewals(db), 0)
            provision.assert_not_called()
        self.assertEqual(sub.plan_id, 5)

    def test_different_plan_renews_without_reprovisioning_or_rotating_credentials(self):
        sub = self.subscription(
            status=SubscriptionStatus.EXPIRED,
            expires_at=datetime.utcnow() - timedelta(seconds=1),
            plan_id=None,
        )
        pending = self.pending()
        pending.plan_id = 10
        db = FakeDB([Result(items=[22]), Result(value=sub), Result(value=pending)])
        previous_password = sub.account_password_encrypted
        previous_username = sub.account_username
        with patch.object(service, "provision_reserved_plan_at_cutover") as provision, \\
             patch.object(service, "reset_subscription_period_usage",
                          side_effect=lambda db, item, **kw: setattr(item, "traffic_used_bytes", 0)), \\
             patch.object(service, "queue_subscription_enforcement") as enforce, \\
             patch.object(service, "history"):
            self.assertEqual(service.activate_due_renewals(db), 1)
            provision.assert_not_called()
            enforce.assert_called_once()
        self.assertEqual(sub.plan_id, 10)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(sub.account_username, previous_username)
        self.assertEqual(sub.account_password_encrypted, previous_password)
        self.assertEqual(sub.traffic_used_bytes, 0)
        self.assertEqual(sub.traffic_limit_bytes, pending.traffic_bytes)
        self.assertEqual(pending.status, "activated")

    def test_cross_plan_provision_errors_cannot_block_paid_renewal(self):
        sub = self.subscription(traffic_used_bytes=10 * 1024**3)
        pending = self.pending()
        pending.plan_id = 10
        db = FakeDB([Result(items=[22]), Result(value=sub), Result(value=pending)])
        with patch.object(service, "provision_reserved_plan_at_cutover",
                          side_effect=RuntimeError("node offline")) as provision, \\
             patch.object(service, "reset_subscription_period_usage",
                          side_effect=lambda db, item, **kw: setattr(item, "traffic_used_bytes", 0)), \\
             patch.object(service, "queue_subscription_enforcement"), \\
             patch.object(service, "history"):
            self.assertEqual(service.activate_due_renewals(db), 1)
            provision.assert_not_called()
        self.assertEqual(pending.status, "activated")
        self.assertEqual(sub.traffic_used_bytes, 0)
        self.assertEqual(sub.plan_id, 10)

    def test_existing_plan_renewal_does_not_require_active_catalog_listing(self):
        sub = self.subscription()
        db = ReservationDB(sub, None)
        item = service.reserve_renewal(
            db, subscription_id=22, plan_id=5, plan_name="archived current",
            traffic_bytes=10 * 1024**3, duration_days=30,
            source="admin", reference="same-plan-archived", actor="admin:1")
        self.assertEqual(item.status, "queued")
        self.assertEqual(item.plan_id, 5)
        self.assertEqual(sub.plan_id, 5)

    def test_days_only_renewal_retains_quota_instead_of_unlimited(self):
        sub = self.subscription()
        db = ReservationDB(sub, SimpleNamespace(duration_days=30,is_active=True))
        row = service.reserve_renewal(
            db, subscription_id=22, plan_id=5, plan_name="original",
            traffic_bytes=0, duration_days=30, source="admin",
            reference="days-only", actor="admin:1")
        self.assertEqual(row.traffic_bytes, 10 * 1024**3)
        self.assertEqual(row.duration_days, 30)
        self.assertEqual(sub.traffic_used_bytes, 4 * 1024**3)

    def test_traffic_only_renewal_retains_plan_duration(self):
        sub = self.subscription()
        db = ReservationDB(sub, SimpleNamespace(duration_days=45,is_active=True))
        row = service.reserve_renewal(
            db, subscription_id=22, plan_id=5, plan_name="original",
            traffic_bytes=20 * 1024**3, duration_days=0,
            source="reseller", reference="traffic-only", actor="reseller:1")
        self.assertEqual(row.traffic_bytes, 20 * 1024**3)
        self.assertEqual(row.duration_days, 45)

    def test_missing_period_fallback_rejected_instead_of_creating_unlimited_account(self):
        sub = self.subscription(activation_duration_days=0, starts_at=None)
        db = ReservationDB(sub)
        with self.assertRaises(Exception) as caught:
            service.reserve_renewal(
                db, subscription_id=22, plan_id=5, plan_name="original",
                traffic_bytes=20 * 1024**3, duration_days=0,
                source="admin", reference="missing-duration", actor="admin:1")
        self.assertEqual(getattr(caught.exception, "status_code", None), 422)

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

    def test_cancelled_account_does_not_consume_reserved_period(self):
        sub = self.subscription(
            status=SubscriptionStatus.CANCELED,
            traffic_used_bytes=10 * 1024**3,
        )
        pending = self.pending()
        db = FakeDB([Result(items=[22]), Result(value=sub), Result(value=pending)])
        with patch.object(service, "reset_subscription_period_usage") as reset, \
             patch.object(service, "queue_subscription_enforcement") as enforce, \
             patch.object(service, "history"):
            self.assertEqual(service.activate_due_renewals(db), 0)
            reset.assert_not_called()
            enforce.assert_not_called()
        self.assertEqual(pending.status, "blocked")
        self.assertEqual(sub.traffic_used_bytes, 10 * 1024**3)

    def test_verified_quota_suspension_is_restored_after_renewal(self):
        sub = self.subscription(status=SubscriptionStatus.SUSPENDED,
                                traffic_used_bytes=10 * 1024**3)
        pending = self.pending()
        db = FakeDB([Result(items=[22]), Result(value=sub), Result(value=pending)])
        with patch.object(service, "verified_quota_suspension", return_value=True), \
             patch.object(service, "reset_subscription_period_usage",
                          side_effect=lambda db, sub, **kw: setattr(sub, "traffic_used_bytes", 0)), \
             patch.object(service, "queue_subscription_enforcement") as enforce, \
             patch.object(service, "history"):
            self.assertEqual(service.activate_due_renewals(db), 1)
            enforce.assert_called_once()
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(pending.status, "activated")
        self.assertEqual(sub.traffic_used_bytes, 0)

    def test_ambiguous_suspension_does_not_consume_paid_renewal(self):
        sub = self.subscription(status=SubscriptionStatus.SUSPENDED,
                                traffic_used_bytes=10 * 1024**3)
        pending = self.pending()
        db = FakeDB([Result(items=[22]), Result(value=sub), Result(value=pending)])
        with patch.object(service, "verified_quota_suspension", return_value=False), \
             patch.object(service, "reset_subscription_period_usage") as reset, \
             patch.object(service, "queue_subscription_enforcement") as enforce, \
             patch.object(service, "history"):
            self.assertEqual(service.activate_due_renewals(db), 0)
            reset.assert_not_called()
            enforce.assert_not_called()
        self.assertEqual(pending.status, "blocked")
        self.assertEqual(sub.traffic_used_bytes, 10 * 1024**3)
        self.assertEqual(sub.status, SubscriptionStatus.SUSPENDED)

    def test_manual_suspension_is_not_lifted(self):
        sub = self.subscription(status=SubscriptionStatus.SUSPENDED,
                                expires_at=datetime.utcnow() - timedelta(seconds=1))
        pending = self.pending()
        db = FakeDB([Result(items=[22]), Result(value=sub), Result(value=pending)])
        with patch.object(service, "reset_subscription_period_usage"), \
             patch.object(service, "queue_subscription_enforcement") as enforce, \
             patch.object(service, "history"):
            self.assertEqual(service.activate_due_renewals(db), 0)
            enforce.assert_not_called()
        self.assertEqual(sub.status, SubscriptionStatus.SUSPENDED)
        self.assertEqual(pending.status, "blocked")

if __name__ == "__main__":
    unittest.main()
