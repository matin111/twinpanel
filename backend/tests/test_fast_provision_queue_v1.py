"""Durable new-account job queue contracts (SQLite unit fixture, no SSH).

PostgreSQL SKIP LOCKED behavior is additionally enforced by production SQL
dialect and live-node canary; these unit tests verify state transitions.
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.fast_provision_job_models_v1 import FastProvisionJobV1
from app.models import SubscriptionStatus
from app.services.fast_provision_queue_v1 import (
    LEASE_SECONDS,
    claim_next_job,
    enqueue_new_subscription,
    fast_provision_queue_enabled,
    finish_job,
    provision_job_status,
    renew_lease,
)
from app.services.fast_provision_worker_v1 import _eligible_new_subscription


class DurableProvisionQueueContracts(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        FastProvisionJobV1.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.now = datetime(2026, 11, 6, 7, 30, 0)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def insert(self, sub_id, *, priority=100, created_at=None):
        job = enqueue_new_subscription(self.db, sub_id, ["anytls", "tuic", "anytls"])
        job.priority = priority
        job.created_at = created_at or self.now
        job.run_after = self.now
        self.db.commit()

    def test_feature_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(fast_provision_queue_enabled())

    def test_priority_claim_and_idempotent_durable_status(self):
        self.insert(100, priority=10)
        self.insert(101, priority=100)
        picked = claim_next_job(self.db, now=self.now)
        self.assertEqual(picked.subscription_id, 101)
        self.assertEqual(picked.requested_protocols, ("anytls", "tuic"))
        self.assertEqual(picked.attempts, 1)
        snapshot = provision_job_status(self.db, 101)
        self.assertEqual(snapshot["state"], "running")
        self.assertEqual(snapshot["priority"], 100)
        self.assertTrue(renew_lease(self.db, picked, now=self.now))
        self.assertTrue(finish_job(self.db, picked, state="done", now=self.now))
        self.assertFalse(finish_job(self.db, picked, state="retry", now=self.now))
        self.assertEqual(provision_job_status(self.db, 101)["state"], "done")
        self.assertEqual(claim_next_job(self.db, now=self.now).subscription_id, 100)

    def test_expired_lease_recovers_after_crash(self):
        self.insert(201)
        first = claim_next_job(self.db, now=self.now)
        self.assertIsNone(claim_next_job(self.db, now=self.now + timedelta(seconds=5)))
        later = self.now + timedelta(seconds=LEASE_SECONDS + 1)
        second = claim_next_job(self.db, now=later)
        self.assertEqual(second.subscription_id, first.subscription_id)
        self.assertNotEqual(second.lease_token, first.lease_token)
        self.assertEqual(second.attempts, 2)
        self.assertFalse(finish_job(self.db, first, state="done", now=later))
        self.assertTrue(finish_job(self.db, second, state="retry", now=later))
        self.assertEqual(provision_job_status(self.db, 201)["state"], "retry")
        self.assertIsNone(claim_next_job(self.db, now=later))
        self.assertEqual(
            claim_next_job(self.db, now=later + timedelta(seconds=60)).attempts, 3
        )

    def test_invalid_payload_does_not_block_other_jobs(self):
        self.insert(301)
        self.insert(302)
        row = self.db.get(FastProvisionJobV1, 301)
        row.requested_protocols_json = '{"invalid":true}'
        row.priority = 101
        self.db.commit()
        self.assertIsNone(claim_next_job(self.db, now=self.now))
        self.assertEqual(provision_job_status(self.db, 301)["state"], "failed")
        self.assertEqual(claim_next_job(self.db, now=self.now).subscription_id, 302)

    def test_only_live_unexpired_accounts_can_provision(self):
        sub = SimpleNamespace(
            status=SubscriptionStatus.ACTIVE,
            expires_at=None, traffic_limit_bytes=100, traffic_used_bytes=99,
        )
        self.assertTrue(_eligible_new_subscription(sub))
        sub.traffic_used_bytes = 100
        self.assertFalse(_eligible_new_subscription(sub))
        sub.traffic_used_bytes = 0
        sub.status = SubscriptionStatus.SUSPENDED
        self.assertFalse(_eligible_new_subscription(sub))
        sub.status = SubscriptionStatus.ACTIVE
        sub.expires_at = datetime.utcnow() - timedelta(seconds=10)
        self.assertFalse(_eligible_new_subscription(sub))
        sub.expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        self.assertTrue(_eligible_new_subscription(sub))
        sub.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        self.assertFalse(_eligible_new_subscription(sub))


if __name__ == "__main__":
    unittest.main()
