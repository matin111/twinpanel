"""Safety/performance regression for admin online and subscriptions snapshots."""
import ast
import pathlib
import threading
import time
import unittest

SRC=(pathlib.Path(__file__).resolve().parents[1]/"app/routers/runtime_endpoints.py").read_text(encoding="utf-8")

class OnlineSnapshotTests(unittest.TestCase):
    def test_read_only_bounded_cache_and_canonical_presence(self):
        ast.parse(SRC)
        self.assertIn("_LIVE_ACTIVITY_SECONDS = 180",SRC)
        self.assertIn("_LIVE_UNCERTAIN_SECONDS = 900",SRC)
        self.assertIn("_LIVE_SNAPSHOT_TTL_SECONDS = 5.0",SRC)
        self.assertIn("_live_snapshot_lock = threading.Lock()",SRC)
        self.assertIn("def _subscription_live_states_uncached(db: Session)",SRC)
        self.assertIn("def _subscription_live_states(db: Session)",SRC)
        self.assertIn("fresh = _subscription_live_states_uncached(db)",SRC)
        self.assertIn("QuotaSession.status == \"active\"",SRC)
        self.assertIn("QuotaUsageEvent.accepted_bytes > 0",SRC)
        self.assertIn("last_seen_at >= cutoff",SRC)

    def test_snapshot_singleflight_expiration_and_error_retry(self):
        # Extract pure cache declarations/wrapper without importing VPN runtime.
        module=ast.parse(SRC)
        nodes=[n for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in
            ("_LIVE_SNAPSHOT_TTL_SECONDS","_live_snapshot_lock","_live_snapshot_cached_at") for t in n.targets)]
        nodes += [n for n in module.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=="_live_snapshot_cache"]
        nodes += [n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=="_subscription_live_states"]
        namespace={"threading":threading,"time":time,"Session":object}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),"<cache-test>","exec"),namespace)
        calls=[]
        def read(db):
            calls.append(db)
            if db=="fail": raise RuntimeError("database unavailable")
            return {len(calls):{"online":True}}
        namespace["_subscription_live_states_uncached"]=read
        get=namespace["_subscription_live_states"]
        self.assertEqual(get("one"),get("two"))
        self.assertEqual(len(calls),1)
        prior = get("two")
        namespace["_live_snapshot_cached_at"]-=6
        self.assertNotEqual(get("new"),prior)
        self.assertEqual(len(calls),2)
        namespace["_live_snapshot_cached_at"]-=6
        with self.assertRaises(RuntimeError):get("fail")
        self.assertEqual(len(calls),3)
        self.assertEqual(get("retry"),{4:{"online":True}})

    def test_no_inference_from_active_subscription_alone(self):
        self.assertIn('return {sid for sid, item in _subscription_live_states(db).items() if item["online"]}',SRC)
        self.assertIn('Subscription.status == SubscriptionStatus.ACTIVE',SRC)
        self.assertIn('QuotaSession.last_seen_at >= cutoff',SRC)
        self.assertIn('QuotaUsageEvent.reported_at >= cutoff',SRC)

if __name__ == "__main__":
    unittest.main()
