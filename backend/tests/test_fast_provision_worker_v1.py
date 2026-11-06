"""Mocked worker outcomes; no SSH or production database."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from app.models import SubscriptionStatus
from app.services.fast_provision_queue_v1 import ClaimedProvisionJob
from app.services.fast_provision_worker_v1 import _provision_claim


def claim(attempts=1):
    return ClaimedProvisionJob(
        subscription_id=998, requested_protocols=("anytls", "hysteria2"),
        lease_token="test-lease", attempts=attempts,
    )


class WorkerOutcomeContracts(unittest.TestCase):
    def run_case(self, *, attempts=1, missing=None, response=None, exception=None,
                 active=True):
        sub = SimpleNamespace(
            status=SubscriptionStatus.ACTIVE if active else SubscriptionStatus.SUSPENDED,
            expires_at=None, traffic_limit_bytes=100, traffic_used_bytes=0,
        )
        db = MagicMock()
        db.get.return_value = sub
        provision = AsyncMock(
            return_value=response or {"ok": True, "quota": {"ok": True}, "errors": []},
            side_effect=exception,
        )
        with patch("app.services.fast_provision_worker_v1.SessionLocal", return_value=db), \
             patch("app.routers.modern_account_delivery_v1.provision_new_account_fast_v1", provision), \
             patch("app.routers.subscription_admin_v2._missing_provisioned_protocols",
                   return_value=missing or []), \
             patch("app.routers.subscription_admin_v2._fail_created_subscription") as fail:
            outcome = asyncio.run(_provision_claim(claim(attempts)))
            return outcome, provision.await_count, fail.call_count

    def test_success(self):
        self.assertEqual(self.run_case(), (("done", None), 1, 0))

    def test_retry_and_terminal_degraded(self):
        response = {"ok": False, "quota": {"ok": True},
                    "errors": [{"protocol": "hysteria2"}]}
        args = {"missing": ["hysteria2"], "response": response}
        self.assertEqual(
            self.run_case(attempts=1, **args),
            (("retry", "missing_protocols"), 1, 0),
        )
        self.assertEqual(
            self.run_case(attempts=4, **args),
            (("degraded", "missing_protocols"), 1, 0),
        )

    def test_no_valid_credential_fails_closed(self):
        self.assertEqual(
            self.run_case(attempts=4, missing=["anytls", "hysteria2"],
                          response={"ok": False, "quota": {"ok": False}}),
            (("failed", "quota_not_synchronized"), 1, 1),
        )

    def test_manual_guard_conflict_never_suspends(self):
        self.assertEqual(
            self.run_case(
                attempts=4, missing=["anytls", "hysteria2"],
                exception=HTTPException(status_code=409, detail="locked"),
            ),
            (("retry", "provisioning_conflict"), 1, 0),
        )

    def test_ineligible_subscription_not_provisioned(self):
        self.assertEqual(
            self.run_case(active=False),
            (("cancelled", "subscription is not eligible"), 0, 0),
        )


if __name__ == "__main__":
    unittest.main()
