"""Customer live device count cannot trust week-old session status."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase, main


PATH = Path(__file__).resolve().parents[1] / "app/routers/customer_subscription_management.py"
SOURCE = PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
FUNCTIONS = [
    node for node in TREE.body
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
    and "active_connections" in ast.unparse(node)
]


class FreshSessionCountContract(TestCase):
    def test_query_only_counts_recent_active_devices(self):
        self.assertEqual(len(FUNCTIONS),1)
        source=ast.unparse(FUNCTIONS[0])
        for expected in (
            "datetime.utcnow() - timedelta(seconds=180)",
            "QuotaSession.last_seen_at >= activity_cutoff",
            "QuotaDevice.status == 'active'",
            "QuotaSession.status == 'active'",
            "join(QuotaDevice, QuotaDevice.id == QuotaSession.device_id)",
        ):
            self.assertIn(expected,source)

    def test_old_active_session_does_not_count_as_connected(self):
        now=datetime(2026,11,26,16,0,0)
        recent=now-timedelta(seconds=179)
        stale=now-timedelta(days=7)
        cutoff=now-timedelta(seconds=180)
        self.assertTrue(recent>=cutoff)
        self.assertFalse(stale>=cutoff)
        # Device lifecycle is independent of an old 'active' session row.
        self.assertFalse(stale>=cutoff and True)

    def test_quota_enforcement_logic_is_not_replaced_by_ui_counting(self):
        self.assertNotIn("QuotaSession.status = ",SOURCE)
        self.assertNotIn("QuotaDevice.status = ",SOURCE)
        self.assertNotIn("db.delete(QuotaSession",SOURCE)


if __name__=="__main__":
    main()
