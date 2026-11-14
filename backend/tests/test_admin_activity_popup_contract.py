"""Static regression guard for the non-invasive administrator activity popup."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class AdminActivityPopupContract(unittest.TestCase):
    def test_admin_only_api_and_metadata_redaction(self):
        api = (ROOT/"backend/app/routers/admin_activity_v1.py").read_text()
        self.assertIn("dependencies=[Depends(require_admin)]", api)
        self.assertIn("safe_keys", api)
        self.assertNotIn('"password"', api)
        self.assertNotIn('"token"', api)

    def test_mutation_audit_avoids_body_and_never_breaks_write(self):
        audit = (ROOT/"backend/app/admin_mutation_audit_middleware_v1.py").read_text()
        self.assertIn('if not user or not user.is_active', audit)
        self.assertIn('request.method not in _MUTATIONS', audit)
        self.assertIn('db.commit()', audit)
        self.assertIn('except Exception:', audit)
        self.assertNotIn("await request.body()", audit)

    def test_wallet_and_renewal_have_detailed_log(self):
        wallet = (ROOT/"backend/app/routers/wallet_admin_v2.py").read_text()
        renewal = (ROOT/"backend/app/routers/account_delivery.py").read_text()
        self.assertIn('action="wallet_credit" if amount > 0 else "wallet_debit"', wallet)
        self.assertIn('"previous_balance_toman": before_balance', wallet)
        self.assertIn('"new_balance_toman": int(result.get("balance_toman") or 0)', wallet)
        self.assertIn('action="subscription_renew_or_reset"', renewal)
        self.assertIn('"previous_traffic_limit_bytes": before_limit', renewal)

    def test_activity_button_replaces_inert_search_without_page_changes(self):
        ui = (ROOT/"components/ui.tsx").read_text()
        popup = (ROOT/"components/admin-activity-popup.tsx").read_text()
        self.assertIn('<div className="search"><AdminActivityPopup/></div>', ui)
        self.assertNotIn('placeholder={pick("جستجو در پنل..."', ui)
        self.assertIn("createPortal(", popup)
        self.assertIn("getCustomerToken()", popup)


if __name__ == "__main__":
    unittest.main()
