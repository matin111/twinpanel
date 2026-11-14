"""Regression guards for reseller-only traffic reset without renewal."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class ResellerResetContract(unittest.TestCase):
    def test_api_requires_ownership_and_uses_locked_audited_reset(self):
        src = (ROOT/"backend/app/routers/reseller_subscription_volume_v2.py").read_text()
        start = src.index('def reset_reseller_subscription_usage(')
        end = src.index('@router.post("/subscriptions/{subscription_id}/extend")', start)
        handler = src[start:end]
        self.assertIn('_owned_link(db, int(reseller.id), subscription_id)', handler)
        self.assertIn('.with_for_update()', handler)
        self.assertIn('origin="reseller_direct", actor_id=str(reseller.id)', handler)
        self.assertIn('reset_subscription_period_usage(', handler)
        self.assertIn('restore_after_period_change(', handler)
        self.assertIn('db.commit()', handler)
        self.assertNotIn('sub.traffic_limit_bytes =', handler)
        self.assertNotIn('sub.expires_at =', handler)
        self.assertNotIn('sub.traffic_used_bytes =', handler)

    def test_reset_preserves_watermarks_and_writes_audit(self):
        src = (ROOT/"backend/app/services/subscription_cycle_reset_v1.py").read_text()
        self.assertIn('"reseller_direct"', src)
        self.assertIn('actor_type="reseller" if origin == "reseller_direct" else "admin"', src)
        self.assertIn('actor_id=actor_id', src)
        self.assertIn('QuotaAuditLog(', src)
        self.assertNotIn('db.delete(', src)

    def test_reseller_ui_requires_confirmation_and_uses_only_reset_endpoint(self):
        ui = (ROOT/"components/reseller-subscriptions-parity.tsx").read_text()
        api = (ROOT/"lib/reseller-runtime-api.ts").read_text()
        self.assertIn('setResetTarget(row)', ui)
        self.assertIn('resetTarget&&createPortal(', ui)
        self.assertIn('onClick={confirmResetUsage}', ui)
        self.assertIn('await resellerApi.resetSubscriptionUsage(id)', ui)
        self.assertIn('/reset-usage', api)

if __name__ == "__main__":
    unittest.main()
