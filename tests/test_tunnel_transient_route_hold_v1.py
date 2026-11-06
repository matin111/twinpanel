"""Regression checks for transient tunnel health-report route holds.

This smoke only loads the pure decision helper, avoiding database bootstrap.
"""
from datetime import datetime, timedelta
from pathlib import Path
import ast
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "backend/app/routers/tunnels.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
helper = next(
    node for node in tree.body if isinstance(node, ast.FunctionDef)
    and node.name == "_transient_route_hold_eligible"
)
scope = {
    "datetime": datetime,
    "_SERVICE_ROUTE_PHYSICAL_HEALTH_MAX_AGE_SECONDS": 90,
    "_SERVICE_ROUTE_TRANSIENT_HOLD_SECONDS": 75,
}
exec(compile(ast.Module(body=[helper], type_ignores=[]), str(SOURCE), "exec"), scope)
eligible = scope["_transient_route_hold_eligible"]


class RouteHoldTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 4, 0, 0)
        self.base = dict(
            is_active=True,
            has_selected_route=True,
            physical_online=True,
            physical_healthy_at=self.now - timedelta(seconds=8),
            failure_started_at=None,
            now=self.now,
        )

    def test_first_transient_failure_keeps_selected_healthy_route(self):
        self.assertTrue(eligible(**self.base))

    def test_a_second_report_during_grace_keeps_route(self):
        self.base["failure_started_at"] = self.now - timedelta(seconds=30)
        self.assertTrue(eligible(**self.base))

    def test_sustained_outage_removes_route(self):
        self.base["failure_started_at"] = self.now - timedelta(seconds=76)
        self.assertFalse(eligible(**self.base))

    def test_physical_carrier_stale_or_offline_does_not_hold(self):
        self.base["physical_online"] = False
        self.assertFalse(eligible(**self.base))
        self.base["physical_online"] = True
        self.base["physical_healthy_at"] = self.now - timedelta(seconds=95)
        self.assertFalse(eligible(**self.base))

    def test_admin_disabled_tunnel_is_never_held(self):
        self.base["is_active"] = False
        self.assertFalse(eligible(**self.base))

    def test_missing_previously_selected_route_is_never_seeded(self):
        self.base["has_selected_route"] = False
        self.assertFalse(eligible(**self.base))


if __name__ == "__main__":
    unittest.main()
