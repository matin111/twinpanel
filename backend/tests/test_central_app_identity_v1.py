"""Dependency-free regressions for tenant scoped reseller usernames."""
from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = ROOT / "backend/app/central_app_identity.py"
spec = importlib.util.spec_from_file_location("central_app_identity_pure", IDENTITY)
assert spec and spec.loader
identity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(identity)


class NamespaceTests(unittest.TestCase):
    def test_namespace_stable_per_installation(self):
        a = identity.installation_namespace("install-abc")
        self.assertRegex(a, r"^TP[A-F0-9]{16}$")
        self.assertEqual(a, identity.installation_namespace("install-abc"))
        self.assertNotEqual(a, identity.installation_namespace("install-def"))

    def test_each_reseller_has_immutable_distinct_prefix(self):
        left = identity.reseller_prefix("install-abc", 1)
        right = identity.reseller_prefix("install-abc", 2)
        other_install = identity.reseller_prefix("install-def", 1)
        self.assertNotEqual(left, right)
        self.assertNotEqual(left, other_install)
        self.assertEqual(left, identity.reseller_prefix("install-abc", 1))
        self.assertTrue(left.startswith(identity.installation_namespace("install-abc") + "_R"))

    def test_account_name_added_exactly_once(self):
        name = identity.prefix_account_name("install-abc", 10, "ali123")
        self.assertEqual(name, identity.reseller_prefix("install-abc", 10) + "ali123")
        self.assertEqual(identity.prefix_account_name("install-abc", 10, name), name)

    def test_no_cross_reseller_impersonation(self):
        foreign = identity.prefix_account_name("install-abc", 9, "ali")
        with self.assertRaisesRegex(ValueError, "username_prefix_conflict"):
            identity.prefix_account_name("install-abc", 10, foreign)
        with self.assertRaisesRegex(ValueError, "username_prefix_conflict"):
            identity.prefix_account_name("install-def", 10, foreign)

    def test_invalid_and_long_usernames_rejected(self):
        for bad in ["", "ali name", "bad/name", "یوزر", "ali@" , "a" * 64]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    identity.prefix_account_name("install-abc", 10, bad)
        with self.assertRaises(ValueError):
            identity.reseller_prefix("install-abc", 0)


class WiringTests(unittest.TestCase):
    def test_only_reseller_factory_calls_pass_scoped_id(self):
        paths = [
            "backend/app/routers/reseller_sale_v2.py",
            "backend/app/routers/reseller_portal.py",
            "backend/app/reseller_manual_subscriptions.py",
            "backend/app/reseller_owned_plans.py",
        ]
        for path in paths:
            with self.subTest(path=path):
                tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
                calls = [
                    node for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "create_subscription_core"
                ]
                self.assertTrue(calls, path)
                self.assertTrue(all(
                    any(kw.arg == "reseller_id" for kw in call.keywords)
                    for call in calls
                ), path)

    def test_original_account_factory_gated(self):
        source = (ROOT / "backend/app/services/subscription_factory.py").read_text()
        self.assertIn("if reseller_id is not None and central_app_entitled():", source)
        self.assertIn("username = prefix_account_name(", source)
        self.assertIn('Subscription.account_username == username', source)

    def test_additive_contact_schema_and_router_registration(self):
        main = (ROOT / "backend/app/main.py").read_text()
        self.assertIn("from .routers.central_app_v1 import router as central_app_v1_router", main)
        self.assertIn("app.include_router(central_app_v1_router)", main)
        router = (ROOT / "backend/app/routers/central_app_v1.py").read_text()
        self.assertIn('@router.get("/public/brand/{token}")', router)
        self.assertIn("ResellerSubscription.subscription_id == sub.id", router)
        self.assertIn("if not central_app_entitled():", router)


if __name__ == "__main__":
    unittest.main()
