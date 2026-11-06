"""Regression: quota sync remains canonical but never stalls the API event loop."""
from __future__ import annotations

import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/app/services/quota_refresh.py"


def isolated_async_wrapper(blocking):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    routine = next(
        x for x in tree.body
        if isinstance(x, ast.AsyncFunctionDef)
        and x.name == "sync_subscription_quota_nodes"
    )
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-quota")
    globals_ = {
        "asyncio": asyncio,
        "_QUOTA_SYNC_EXECUTOR": pool,
        "_sync_subscription_quota_nodes_blocking": blocking,
        "Session": object,
    }
    exec(compile(ast.Module(body=[routine], type_ignores=[]), str(SOURCE), "exec"), globals_)
    return globals_["sync_subscription_quota_nodes"], pool


class NonblockingQuotaSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_quota_scan_does_not_block_api_loop(self):
        main_thread = threading.get_ident()
        events = []
        sessions = []
        def work(db, subscription_id, extras):
            events.append(("thread", threading.get_ident()))
            time.sleep(0.27)
            sessions.append(db)
            return {
                "ok": True, "subscription_id": subscription_id,
                "nodes": [{"node_id": 7, "ok": True, "devices": 1679}],
                "mode": "agent-pull",
            }

        wrapper, pool = isolated_async_wrapper(work)
        try:
            db = object()
            task = asyncio.create_task(wrapper(db, 3594))
            await asyncio.sleep(0.05)
            self.assertFalse(task.done())
            # A small /health-style coroutine must continue while quota scans.
            health = await asyncio.wait_for(asyncio.sleep(0, result="ok"), 0.1)
            self.assertEqual(health, "ok")
            result = await asyncio.wait_for(task, 2)
            self.assertTrue(result["ok"])
            self.assertEqual(result["subscription_id"], 3594)
            self.assertIs(sessions[0], db)
            self.assertNotEqual(events[0][1], main_thread)
        finally:
            pool.shutdown(wait=True)

    async def test_cancellation_waits_for_request_session_safety(self):
        finished = threading.Event()
        def work(db, sub, extras):
            time.sleep(0.22)
            finished.set()
            return {"ok": True, "nodes": [], "mode": "agent-pull"}
        wrapper, pool = isolated_async_wrapper(work)
        try:
            task = asyncio.create_task(wrapper(object(), 11))
            await asyncio.sleep(0.04)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            # Session dependency can now close safely, never during quota work.
            self.assertTrue(finished.is_set())
        finally:
            pool.shutdown(wait=True)

    def test_canonical_quota_logic_kept_in_sequential_executor(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("max_workers=1", source)
        self.assertIn("with db.begin_nested():", source)
        self.assertIn("generated = sync_node_config(", source)
        self.assertIn("await asyncio.shield(future)", source)
        self.assertIn('"mode": "agent-pull"', source)


if __name__ == "__main__":
    unittest.main()
