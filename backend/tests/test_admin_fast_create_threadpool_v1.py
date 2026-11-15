"""Guard against synchronous subscription creation blocking the API event loop."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class AdminFastCreateThreadpoolTest(unittest.TestCase):
    def test_create_endpoint_uses_fastapi_sync_threadpool(self):
        tree = ast.parse((ROOT / "app/routers/subscription_create_fast_v1.py").read_text())
        fn = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "admin_create_fast_v1"), None)
        self.assertIsNotNone(fn)
        self.assertIsInstance(fn, ast.FunctionDef, "Synchronous SQLAlchemy create must not block the event loop")

    def test_frontend_does_not_abort_committed_create_or_retry_automatically(self):
        js = (ROOT.parent / "lib/subscription-create-fast-api.ts").read_text()
        # A timed-out POST may already have committed a durable subscription.
        # Backend acceptance is the authoritative completion signal.
        self.assertNotIn("new AbortController()", js)
        self.assertNotIn("signal:controller.signal", js)
        self.assertIn("/v1/subscriptions/admin-create-fast-v1", js)
        self.assertIn("body:JSON.stringify(payload)", js)
        self.assertNotIn("retry", js.split("export async function createSubscriptionFastV1", 1)[1])

if __name__ == "__main__":
    unittest.main()
