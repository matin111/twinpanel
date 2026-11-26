"""Prevent resurgence of per-subscriber queries in reseller account listings."""
from __future__ import annotations

import ast
import inspect
import unittest

from app.routers import reseller_portal


class ResellerBulkReadContract(unittest.TestCase):
    def test_account_listing_has_no_sql_inside_per_row_loop(self):
        source = inspect.getsource(reseller_portal.reseller_subscriptions)
        tree = ast.parse(source)
        loops = [n for n in ast.walk(tree) if isinstance(n,(ast.For,ast.AsyncFor))]
        self.assertTrue(any(isinstance(n.iter,ast.Name) and n.iter.id == "rows" for n in loops))
        for node in loops:
            if not isinstance(node.iter,ast.Name) or node.iter.id != "rows":
                continue
            calls = [n for child in node.body for n in ast.walk(child)
                     if isinstance(n,ast.Call)]
            forbidden = [n for n in calls if isinstance(n.func,ast.Attribute)
                         and n.func.attr in {"query","get","execute","scalar","scalars"} 
                         and isinstance(n.func.value,ast.Name)
                         and n.func.value.id == "db"]
            self.assertFalse(forbidden,"Per-account SQL reintroduced")

    def test_batch_lookups_and_overrides_present(self):
        source=inspect.getsource(reseller_portal.reseller_subscriptions)
        for entity in ("Subscription","User","Plan","SubscriptionProtocol",
                       "SubscriptionNode","SubscriptionRuntimeOverride"):
            self.assertIn("db.query("+entity,source)
        self.assertIn("overrides_by_id.get(int(sub.id))",source)
        self.assertIn("protocols_by_subscription.get(int(sub.id)",source)


if __name__=="__main__":
    unittest.main()
