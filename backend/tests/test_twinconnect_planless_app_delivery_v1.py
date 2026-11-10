"""Regression: app delivery works for migrated subscriptions with plan_id=NULL.

Pure-function fixtures: no live database, secrets, licensing or VPN mutations.
"""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
CREDENTIAL_SOURCE = ROOT / "app/central_app_credentials.py"
ROUTER_SOURCE = ROOT / "app/routers/central_app_credentials_v1.py"


def plan_type_function():
    source = ast.parse(CREDENTIAL_SOURCE.read_text(encoding="utf-8"))
    fn = next(n for n in source.body
              if isinstance(n, ast.FunctionDef) and n.name == "_plan_type_code")
    fn.decorator_list = []
    fn.args.args[0].annotation = None
    fn.args.args[1].annotation = None
    fn.returns = None
    # Stub models are only identity tokens. DB is never touched outside the
    # simulated queries.
    class Code:
        type_name = "name"
    class Category:
        plan_id = "plan_id"
    class Query:
        def __init__(self, is_category, group=None):
            self.is_category = is_category
            self.group = group
        def filter(self, *_):
            return self
        def first(self):
            return self.group if self.is_category else SimpleNamespace(id=7)
    class Db:
        def __init__(self):
            self.category_lookups = 0
        def query(self, model):
            if model is Category:
                self.category_lookups += 1
                return Query(True, SimpleNamespace(subscription_type="Premium"))
            return Query(False)
    import contextlib
    scope = {
        "PlanCategoryAssignment": Category,
        "AppPlanTypeCode": Code,
        "IntegrityError": Exception,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]),
                 str(CREDENTIAL_SOURCE), "exec"), scope)
    return scope["_plan_type_code"], Db


class LegacyAppDeliveryTests(unittest.TestCase):
    def test_missing_plan_uses_generic_type_without_category_lookup(self):
        fn, Db = plan_type_function()
        db = Db()
        subscription = SimpleNamespace(id=3594, plan_id=None)
        self.assertEqual(fn(db, subscription), 7)
        self.assertEqual(db.category_lookups, 0)
        self.assertIsNone(subscription.plan_id)

    def test_existing_plan_still_resolves_its_category(self):
        fn, Db = plan_type_function()
        db = Db()
        self.assertEqual(fn(db, SimpleNamespace(plan_id=41)), 7)
        self.assertEqual(db.category_lookups, 1)

    def test_session_plan_reports_unassigned_without_inventing_plan(self):
        router = ROUTER_SOURCE.read_text(encoding="utf-8")
        self.assertIn('plan_id = getattr(sub, "plan_id", None)', router)
        self.assertIn('"plan_id": int(plan.id) if plan else 0', router)
        self.assertIn('"device_limit": int(plan.device_limit) if plan', router)
        self.assertNotIn('plan = db.get(Plan, int(sub.plan_id))', router)

    def test_no_vpn_credentials_or_subscription_plan_ever_changed(self):
        src = CREDENTIAL_SOURCE.read_text(encoding="utf-8")
        fn = ast.parse(src)
        selected = next(n for n in fn.body
                        if isinstance(n, ast.FunctionDef) and n.name == "_plan_type_code")
        changes = [n for n in ast.walk(selected) if isinstance(n, ast.Assign)]
        self.assertFalse(any(
            isinstance(target, ast.Attribute)
            and target.attr in {"plan_id", "account_password_encrypted",
                                "account_username"}
            for n in changes for target in n.targets
        ))


if __name__ == "__main__":
    unittest.main()
