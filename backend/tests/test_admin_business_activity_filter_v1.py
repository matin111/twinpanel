"""Admin history shows meaningful business actions, not HTTP plumbing."""
import ast
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]

class AdminHistoryFilterContract(unittest.TestCase):
    def test_middleware_only_records_business_mutations(self):
        source=(ROOT/"backend/app/admin_mutation_audit_middleware_v1.py").read_text()
        ast.parse(source)
        self.assertIn("matched is None", source)
        self.assertNotIn('action="manual_api_mutation"', source)
        self.assertIn('"subscription_edit"', source)
        self.assertIn('"user_edit"', source)
        self.assertNotIn('request.body()', source)
        self.assertNotIn('"/v1/admin/system/release/check"',source)
        self.assertIsNotNone(re.compile(r"^/v1/subscriptions/(\d+)/admin-edit$").match("/v1/subscriptions/123/admin-edit"))

    def test_legacy_http_noise_is_excluded_without_deleting_records(self):
        source=(ROOT/"backend/app/routers/admin_activity_v1.py").read_text()
        ast.parse(source)
        self.assertGreaterEqual(source.count('QuotaAuditLog.action != "manual_api_mutation"'),2)
        self.assertNotIn("db.delete(",source)

    def test_popup_uses_business_labels_only(self):
        source=(ROOT/"components/admin-activity-popup.tsx").read_text()
        self.assertIn('subscription_edit:"ویرایش اشتراک"',source)
        self.assertIn('user_edit:"ویرایش کاربر"',source)
        self.assertNotIn('manual_api_mutation:"تغییر دستی در پنل"',source)

if __name__=="__main__":
    unittest.main()
