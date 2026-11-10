"""TwinConnect must reuse TwinPanel's existing signed vendor license.

These integration guards deliberately do not call the vendor or change a
customer's licenses, bot link lookup, VPN credentials, or server profiles.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = ROOT / "backend/app/central_app_identity.py"
PANEL_ROUTES = ROOT / "backend/app/routers/central_app_v1.py"
APP_ROUTES = ROOT / "backend/app/routers/central_app_credentials_v1.py"
CLIENT = ROOT / "clients/twinconnect/lib/tenant_api.dart"
BOT_LINK = ROOT / "backend/app/reseller_bot_subscription_link_runtime.py"


class ExistingLicenseIntegrationContract(unittest.TestCase):
    def test_app_entitlement_reuses_signed_panel_license(self):
        identity = IDENTITY.read_text(encoding="utf-8")
        self.assertIn("load_license_state()", identity)
        self.assertIn("_verify_entitlement(token)", identity)
        self.assertIn('verified.get("app_enabled") is True', identity)
        self.assertIn('"central_app" in (verified.get("features") or [])', identity)
        self.assertIn('verified.get("status") == "active"', identity)

    def test_panel_registration_uses_existing_vendor_and_installation_id(self):
        routes = PANEL_ROUTES.read_text(encoding="utf-8")
        registration = routes.split('@router.post("/admin/register")', 1)[1].split(
            '@router.get("/admin/profile")', 1
        )[0]
        self.assertIn("Depends(require_admin)", registration)
        self.assertIn("central_app_entitled()", registration)
        self.assertIn("load_license_state()", registration)
        self.assertIn("ensure_installation_id()", registration)
        self.assertIn('"/v1/app/register"', registration)
        self.assertIn('"signed_entitlement": token', registration)
        self.assertIn('"installation_id": installation_id', registration)

    def test_vendor_lookup_only_gets_namespace_and_login_goes_to_panel(self):
        client = CLIENT.read_text(encoding="utf-8")
        self.assertIn("'/v1/app/resolve/${Uri.encodeComponent(namespace)}'", client)
        self.assertIn("panel.apiOrigin.resolve('/v1/central-app/public/login')", client)
        self.assertIn("'username': username.trim()", client)
        self.assertIn("'password': password", client)
        self.assertNotIn("vendorOrigin.resolve('/v1/central-app/public/login')", client)

    def test_app_license_not_added_to_bot_link_lookup(self):
        bot = BOT_LINK.read_text(encoding="utf-8")
        self.assertIn("username = State()", bot)
        self.assertIn("_share_url(db, sub)", bot)
        self.assertNotIn("app_delivery_payload", bot)
        self.assertNotIn("central_app_entitled", bot)

    def test_app_login_remains_separate_from_bot_link_lookup(self):
        routes = APP_ROUTES.read_text(encoding="utf-8")
        self.assertIn('@router.post("/public/login")', routes)
        self.assertIn("authenticate_app(db, payload.username, payload.password)", routes)


if __name__ == "__main__":
    unittest.main()
