"""Regression: contested reseller purchase never charges twice or leaks a 500."""
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.routers import reseller_traffic_purchase_v3 as subject


class FakePGError(Exception):
    def __init__(self, code: str):
        self.pgcode = code


def db_lock_error(code: str = "55P03") -> OperationalError:
    return OperationalError("SELECT ... FOR UPDATE", {}, FakePGError(code))


class PurchaseLockRetryTests(TestCase):
    def setUp(self):
        self.payload = subject.BuyTrafficIn(package_id=1, idempotency_key="purchase-test-123")
        self.reseller = SimpleNamespace(id=123)
        self.db = MagicMock()

    def test_busy_lock_retries_same_purchase_without_changing_key(self):
        calls = []
        def once(payload, reseller_id, db):
            calls.append((payload.idempotency_key, reseller_id, db))
            if len(calls) == 1:
                raise db_lock_error()
            return {"ok": True, "duplicate": False}
        with patch.object(subject, "_buy_traffic_once", side_effect=once), patch.object(subject.time,"sleep"):
            result = subject.buy_traffic_and_restore(self.payload,self.reseller,self.db)
        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 2)
        self.assertEqual([r[0] for r in calls], ["purchase-test-123"]*2)
        self.assertEqual([r[1] for r in calls], [123]*2)
        self.db.rollback.assert_called_once()

    def test_persistent_lock_becomes_retryable_503_not_500(self):
        with patch.object(subject, "_buy_traffic_once",side_effect=db_lock_error()), patch.object(subject.time,"sleep"):
            with self.assertRaises(HTTPException) as ctx:
                subject.buy_traffic_and_restore(self.payload,self.reseller,self.db)
        self.assertEqual(ctx.exception.status_code,503)
        self.assertEqual(ctx.exception.headers["Retry-After"],"2")
        self.assertEqual(self.db.rollback.call_count,5)

    def test_non_lock_db_error_propagates(self):
        with patch.object(subject, "_buy_traffic_once",side_effect=db_lock_error("42P01")), patch.object(subject.time,"sleep") as sleep:
            with self.assertRaises(OperationalError):
                subject.buy_traffic_and_restore(self.payload,self.reseller,self.db)
        sleep.assert_not_called()
        self.db.rollback.assert_called_once()


if __name__=="__main__":
    main()
