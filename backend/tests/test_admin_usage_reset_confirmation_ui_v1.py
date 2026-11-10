"""Regression: admin Reset button must use a dedicated yes/no confirmation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = (ROOT / "components/legacy-subscriptions-exact.tsx").read_text(encoding="utf-8")
API = (ROOT / "backend/app/routers/account_delivery.py").read_text(encoding="utf-8")

class DirectResetConfirmationTests(unittest.TestCase):
    def test_card_reset_opens_only_confirmation(self):
        self.assertIn('setResetTarget(item)', VIEW)
        self.assertNotIn('openEdit(item);setEditResetUsage(true)', VIEW)
        self.assertIn('title={pick("تأیید ریست حجم مصرفی","Confirm usage reset")}', VIEW)
        self.assertIn('pick("خیر","No")', VIEW)
        self.assertIn('pick("بله، ریست کن","Yes, reset")', VIEW)

    def test_reset_calls_existing_accounting_safe_endpoint(self):
        self.assertIn('await legacyAdminApi.extendSubscription(subscriptionId,{', VIEW)
        self.assertIn('add_traffic_gb:0,add_days:0,reset_usage:true,reset_date:false', VIEW)
        self.assertIn('if(reset_usage):\n        reset_subscription_period_usage(db,sub,origin="admin_renew")', API)
        self.assertIn('if add_traffic_gb>0:', API)
        self.assertIn('if add_days > 0:', API)

    def test_no_double_submit_and_failure_stays_visible(self):
        self.assertIn('if(!resetTarget||busy)return;', VIEW)
        self.assertIn('disabled={!!busy} onClick={confirmUsageReset}', VIEW)
        self.assertIn('{error&&<Notice error={error} ok=""/>}', VIEW)

if __name__ == "__main__":
    unittest.main()
