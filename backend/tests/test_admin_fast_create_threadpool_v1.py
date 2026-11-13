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

    def test_frontend_has_bounded_wait_without_automatic_retry(self):
        js = (ROOT.parent / "lib/subscription-create-fast-api.ts").read_text()
        self.assertIn("AbortController", js)
        self.assertIn("clearTimeout(timeout)", js)
        self.assertIn("45000", js)
        self.assertIn("قبل از تلاش دوباره", js)

if __name__ == "__main__":
    unittest.main()
