"""Source-level contract without importing app models or touching any database."""
from __future__ import annotations

import ast
from pathlib import Path
from unittest import TestCase, main


ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def function(path: str, name: str) -> ast.FunctionDef:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == name]
    assert len(matches) == 1, (path, name)
    return matches[0]


class FastAdminDashboardTests(TestCase):
    def test_monthly_sum_is_explicitly_optional(self):
        fn = function("admin.py", "dashboard_summary_v2")
        options = [arg.arg for arg in fn.args.kwonlyargs]
        self.assertIn("include_monthly_usage", options)
        index = options.index("include_monthly_usage")
        default = fn.args.kw_defaults[index]
        self.assertIsInstance(default, ast.Constant)
        self.assertIs(default.value, True)
        guarded = [node for node in fn.body if isinstance(node, ast.If)
                   and isinstance(node.test, ast.Name)
                   and node.test.id == "include_monthly_usage"]
        self.assertEqual(len(guarded), 1)
        self.assertEqual(guarded[0].orelse, [])
        self.assertIn("QuotaUsageEvent.billable_bytes", ast.unparse(guarded[0]))
        self.assertIn("QuotaUsageEvent.reported_at", ast.unparse(guarded[0]))
        self.assertNotIn("QuotaUsageEvent.billable_bytes",
                         "\n".join(ast.unparse(node) for node in fn.body if node is not guarded[0]))

    def test_live_routes_skip_legacy_ledger_aggregate(self):
        for path, name in [
            ("admin_user_isolation.py", "dashboard_summary"),
            ("runtime_endpoints.py", "dashboard_summary_live_subscriptions"),
        ]:
            with self.subTest(route=name):
                fn = function(path, name)
                calls = [node for node in ast.walk(fn) if isinstance(node, ast.Call)
                         and isinstance(node.func, (ast.Attribute, ast.Name))
                         and (getattr(node.func, "attr", None) == "dashboard_summary_v2"
                              or getattr(node.func, "id", None) == "dashboard_summary_v2")]
                self.assertEqual(len(calls), 1)
                self.assertTrue(any(key.arg == "include_monthly_usage"
                                    and isinstance(key.value, ast.Constant)
                                    and key.value.value is False for key in calls[0].keywords))


if __name__ == "__main__":
    main()
