"""Opt-in commerce queue contracts; no actual orders, SSH or Telegram sent."""
from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.fast_provision_job_models_v1 import FastProvisionJobV1
from app.services.fast_provision_queue_v1 import (
    ClaimedProvisionJob,
    claim_next_job,
    enqueue_new_subscription,
    fast_provision_commerce_enabled,
    finish_job,
    provision_job_status,
)
from app.services.fast_provision_commerce_completion_v1 import finalize_reseller_bot_job


class CommerceQueueGateContracts(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        FastProvisionJobV1.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.now = datetime.utcnow()
        enqueue_new_subscription(
            self.db, 305, ["anytls", "tuic"], origin="reseller_owned",
        )
        row = self.db.get(FastProvisionJobV1, 305)
        row.created_at = self.now
        row.run_after = self.now
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_admin_flag_does_not_autorun_commerce(self):
        with patch.dict(os.environ, {
            "TWINPANEL_FAST_PROVISION_QUEUE_V1": "true",
            "TWINPANEL_FAST_PROVISION_COMMERCE_V1": "false",
        }):
            self.assertFalse(fast_provision_commerce_enabled())
            self.assertIsNone(claim_next_job(self.db, now=self.now))
        with patch.dict(os.environ, {
            "TWINPANEL_FAST_PROVISION_QUEUE_V1": "true",
            "TWINPANEL_FAST_PROVISION_COMMERCE_V1": "true",
        }):
            job = claim_next_job(self.db, now=self.now)
            self.assertEqual(job.origin, "reseller_owned")
            self.assertEqual(job.requested_protocols, ("anytls", "tuic"))
            self.assertTrue(finish_job(self.db, job, state="done", now=self.now + timedelta(seconds=3)))
            info = provision_job_status(self.db, 305)
            self.assertEqual(info["origin"], "reseller_owned")
            self.assertEqual(info["elapsed_ms"], 3000)

    def test_reject_imported_or_renewal_origin(self):
        for origin in ("migration", "renewal", "reseller_bot_renewal"):
            with self.assertRaises(ValueError):
                enqueue_new_subscription(self.db, 404, ["anytls"], origin=origin)


class ResellerBotCompletionContracts(unittest.TestCase):
    def _mock_case(self, state, *, initial="provisioning"):
        row = SimpleNamespace(
            id=17, reseller_id=11, telegram_id=123456,
            subscription_id=305, status=initial,
            payment_note=None, fulfilled_at=None, error_text=None,
        )
        sub = SimpleNamespace(id=305, account_username="test-user")
        db = MagicMock()
        db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = row
        db.get.return_value = sub
        bot_send = AsyncMock(return_value=True)
        with patch("app.services.fast_provision_commerce_completion_v1.SessionLocal",
                   return_value=db), \
             patch("app.discount_service.redeem_discount_for_order") as redeem, \
             patch("app.routers.reseller_bot_orders._stored_info",
                   return_value={"account": {"username": "test-user"}}), \
             patch("app.routers.reseller_bot_orders._send_order_delivery_to_telegram",
                   bot_send):
            job = ClaimedProvisionJob(
                subscription_id=305, lease_token="lease-test",
                requested_protocols=("anytls",), attempts=1,
                origin="reseller_bot_owned",
            )
            asyncio.run(finalize_reseller_bot_job(job, state, "node_failure"))
            return row, db, redeem, bot_send

    def test_complete_paid_order_only_after_credential_done(self):
        row, db, redeem, send = self._mock_case("done")
        self.assertEqual(row.status, "fulfilled")
        self.assertIsNotNone(row.fulfilled_at)
        self.assertIsNone(row.error_text)
        redeem.assert_called_once()
        send.assert_awaited_once()
        self.assertEqual(db.commit.call_count, 1)
        db.close.assert_called_once()

    def test_failed_provision_does_not_send_or_redeem(self):
        row, db, redeem, send = self._mock_case("failed")
        self.assertEqual(row.status, "provision_failed")
        self.assertEqual(row.error_text, "node_failure")
        redeem.assert_not_called()
        send.assert_not_awaited()
        db.commit.assert_called_once()

    def test_idempotent_fulfilled_order_does_not_notify_twice(self):
        row, db, redeem, send = self._mock_case("done", initial="fulfilled")
        self.assertEqual(row.status, "fulfilled")
        redeem.assert_not_called()
        send.assert_not_awaited()
        db.commit.assert_not_called()

    def test_reseller_owned_nonbot_is_never_customer_bot_fulfilled(self):
        job = ClaimedProvisionJob(
            subscription_id=305, lease_token="lease-test",
            requested_protocols=("anytls",), attempts=1,
            origin="reseller_owned",
        )
        with patch("app.services.fast_provision_commerce_completion_v1.SessionLocal") as session:
            asyncio.run(finalize_reseller_bot_job(job, "done", None))
            session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
