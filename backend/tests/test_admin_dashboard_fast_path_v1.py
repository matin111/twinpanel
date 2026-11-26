"""Fast admin overview must not scan millions of usage rows for unused KPI."""
from __future__ import annotations

import ast
import inspect
import unittest

from app.routers import admin, admin_user_isolation, runtime_endpoints


class DashboardFastPathContract(unittest.TestCase):
    def test_monthly_usage_remains_available_for_legacy_caller(self):
        fn=admin.dashboard_summary_v2
        self.assertTrue(inspect.signature(fn).parameters["include_monthly_usage"].default)
        source=inspect.getsource(fn)
        tree=ast.parse(source)
        candidates=[n for n in ast.walk(tree) if isinstance(n,ast.If)
                    and isinstance(n.test,ast.Name)
                    and n.test.id=="include_monthly_usage"]
        self.assertEqual(len(candidates),1)
        statements=ast.unparse(candidates[0])
        self.assertIn("QuotaUsageEvent.billable_bytes",statements)
        self.assertIn("QuotaUsageEvent.reported_at",statements)
        self.assertEqual(candidates[0].orelse,[])

    def test_live_dashboard_skips_ledger_scan(self):
        for fn in [admin_user_isolation.dashboard_summary,
                   runtime_endpoints.dashboard_summary_live_subscriptions]:
            with self.subTest(fn=fn.__name__):
                self.assertIn("include_monthly_usage=False",inspect.getsource(fn))


if __name__=="__main__":
    unittest.main()
