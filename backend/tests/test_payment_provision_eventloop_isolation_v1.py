"""Paid order isolation: avoid starving FastAPI's event loop during SSH.

All side effects are mocked; tests never provision a node or charge a customer.
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from app.services import payment_fulfillment_fast_path as fast


class PaymentProvisionEventLoopIsolationTests(unittest.TestCase):
    def test_opt_in_keeps_api_loop_responsive_and_session_thread_local(self):
        thread_ids = []
        inner_session = MagicMock(name="provision-session")
        outer_session = MagicMock(name="claim-session")
        main_id = threading.get_ident()

        async def blocking_provision(order_id, session):
            thread_ids.append(threading.get_ident())
            self.assertEqual(order_id, 115)
            self.assertIs(session, inner_session)
            # Simulates synchronous DNS/SQL/SSH code inside an async coroutine.
            time.sleep(0.17)
            return {"status": "fulfilled", "subscription_id": 3801}

        async def exercise():
            start = time.monotonic()
            task = asyncio.create_task(
                fast._fulfill_paid_order_without_blocking_api(115, outer_session)
            )
            await asyncio.sleep(0.025)
            self.assertLess(time.monotonic() - start, 0.12)
            self.assertFalse(task.done())
            result = await task
            self.assertEqual(result["subscription_id"], 3801)

        with patch.dict(os.environ, {"TWINPANEL_PAYMENT_PROVISION_ISOLATED_V1": "true"}), \
             patch.object(fast, "SessionLocal", return_value=inner_session) as maker, \
             patch.object(fast, "_fulfill_paid_order", side_effect=blocking_provision):
            asyncio.run(exercise())
            maker.assert_called_once()
            inner_session.close.assert_called_once()
            outer_session.close.assert_not_called()
            self.assertEqual(len(thread_ids), 1)
            self.assertNotEqual(thread_ids[0], main_id)

    def test_flag_off_preserves_existing_db_session_and_event_loop(self):
        db = MagicMock()
        seen = []

        async def legacy(order_id, session):
            seen.append((order_id, session, threading.get_ident()))
            return {"status": "fulfilled"}

        with patch.dict(os.environ, {}, clear=True), \
             patch.object(fast, "SessionLocal") as maker, \
             patch.object(fast, "_fulfill_paid_order", side_effect=legacy):
            result = asyncio.run(fast._fulfill_paid_order_without_blocking_api(114, db))
            self.assertEqual(result["status"], "fulfilled")
            self.assertEqual(seen, [(114, db, threading.get_ident())])
            maker.assert_not_called()

    def test_worker_session_always_closed_on_failure(self):
        inner_session = MagicMock()

        async def fail(order_id, session):
            raise RuntimeError("synthetic-node-error")

        with patch.dict(os.environ, {"TWINPANEL_PAYMENT_PROVISION_ISOLATED_V1": "1"}), \
             patch.object(fast, "SessionLocal", return_value=inner_session), \
             patch.object(fast, "_fulfill_paid_order", side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, "synthetic-node-error"):
                asyncio.run(fast._fulfill_paid_order_without_blocking_api(17, MagicMock()))
        inner_session.close.assert_called_once()

    def test_cancelled_api_task_does_not_abandon_running_thread(self):
        started = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        inner_session = MagicMock()

        async def slow(order_id, session):
            started.set()
            self.assertTrue(release.wait(timeout=3), "test release timeout")
            finished.set()
            return {"status": "fulfilled"}

        async def scenario():
            task = asyncio.create_task(
                fast._fulfill_paid_order_without_blocking_api(17, MagicMock())
            )
            while not started.is_set():
                await asyncio.sleep(0.002)
            task.cancel()
            await asyncio.sleep(0.015)
            self.assertFalse(task.done())
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(finished.is_set())

        with patch.dict(os.environ, {"TWINPANEL_PAYMENT_PROVISION_ISOLATED_V1": "true"}), \
             patch.object(fast, "SessionLocal", return_value=inner_session), \
             patch.object(fast, "_fulfill_paid_order", side_effect=slow):
            asyncio.run(scenario())
        inner_session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
