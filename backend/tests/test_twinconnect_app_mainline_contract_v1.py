"""Forward-port contract: app login must not mutate VPN identities or deliveries."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "backend/app/main.py"
CREDS = ROOT / "backend/app/central_app_credentials.py"
MODELS = ROOT / "backend/app/central_app_credential_models.py"
ROUTES = ROOT / "backend/app/routers/central_app_credentials_v1.py"
DIRECTORY = ROOT / "backend/app/routers/central_app_v1.py"
IDENTITY = ROOT / "backend/app/central_app_identity.py"
ADMIN = ROOT / "components/legacy-subscriptions-exact.tsx"
RESELLER = ROOT / "components/reseller-subscriptions-parity.tsx"
DELIVERY = ROOT / "components/central-app-brand-manager.tsx"
LINK_MODAL = ROOT / "components/subscription-link-delivery-modal.tsx"
CUSTOMER = ROOT / "components/customer-subscriptions-runtime.tsx"
FRONT_API = ROOT / "lib/central-app-credential-api.ts"
LICENSE = ROOT / "components/license-center.tsx"
ROUTER_UI = ROOT / "components/routed-page-client-v2.tsx"


class TwinConnectMainlineContract(unittest.TestCase):
    def test_all_new_python_modules_parse_and_are_mounted(self):
        for p in (MAIN, CREDS, MODELS, ROUTES, DIRECTORY, IDENTITY):
            with self.subTest(file=p.name):
                ast.parse(p.read_text(encoding="utf-8"))
        main = MAIN.read_text(encoding="utf-8")
        self.assertIn("central_app_credential_models", main)
        self.assertIn("central_app_v1_router", main)
        self.assertIn("app.include_router(central_app_credentials_v1_router)", main)
        self.assertIn("app.include_router(central_app_appearance_v1_router)", main)

    def test_app_credentials_are_independent_and_entitlement_gated(self):
        creds = CREDS.read_text(encoding="utf-8")
        identity = IDENTITY.read_text(encoding="utf-8")
        models = MODELS.read_text(encoding="utf-8")
        self.assertIn('"subscription_app_credentials"', models)
        self.assertIn("password_hash", models)
        self.assertIn("delivery_password_encrypted", models)
        self.assertIn("hash_password(password)", creds)
        self.assertIn("_fernet().encrypt", creds)
        self.assertIn("verify_password(password, row.password_hash)", creds)
        self.assertIn("row.revision += 1", creds)
        self.assertIn("signed_entitlement", identity)
        self.assertIn("verified.get(\"app_enabled\") is True", identity)
        self.assertIn('"central_app" in (verified.get("features") or [])', identity)
        self.assertNotIn("sub.account_password_encrypted = password", creds)

    def test_admin_reseller_and_user_routes_enforce_scope(self):
        routes = ROUTES.read_text(encoding="utf-8")
        for action in (
            '/admin/subscriptions/{subscription_id}/app-delivery',
            '/admin/subscriptions/{subscription_id}/app-password-reset',
            '/reseller/subscriptions/{subscription_id}/app-delivery',
            '/public/login',
        ):
            self.assertIn(action, routes)
        self.assertIn("Depends(require_admin)", routes)
        self.assertIn("Depends(require_reseller)", routes)
        self.assertIn("ResellerSubscription.reseller_id == int(reseller_id)", routes)
        self.assertIn("int(sub.user_id) != int(user.id)", routes)
        self.assertIn('"vpn_credentials_unchanged"', routes)

    def test_frontend_entry_and_vendor_registration_are_reachable(self):
        admin = ADMIN.read_text(encoding="utf-8")
        reseller = RESELLER.read_text(encoding="utf-8")
        delivery = DELIVERY.read_text(encoding="utf-8")
        link = LINK_MODAL.read_text(encoding="utf-8")
        api = FRONT_API.read_text(encoding="utf-8")
        self.assertIn('data-testid="admin-app-delivery-action"', admin)
        self.assertIn("appDeliverySubscriptionId", admin)
        self.assertIn("<AppCredentialDeliveryCard", admin)
        self.assertIn('appOwner="admin"', admin)
        self.assertIn('appOwner="reseller"', reseller)
        self.assertIn('data-testid="reseller-app-delivery-action"', reseller)
        self.assertIn('<AppCredentialDeliveryCard', reseller)
        self.assertIn('owner="reseller"', reseller)
        customer = CUSTOMER.read_text(encoding="utf-8")
        self.assertIn('appOwner="customer"', customer)
        self.assertIn('subscriptionId={linkModalId??undefined}', customer)
        self.assertIn('owner:"admin"|"reseller"|"customer"', api)
        self.assertIn('if(owner==="customer"&&reset)', api)
        self.assertIn('appOwner?:"admin"|"reseller"|"customer"', link)
        self.assertIn('appDelivery.app_username', link)
        self.assertIn('appDelivery.app_password', link)
        self.assertIn('if(open&&appOwner&&subscriptionId&&subscriptionId>0)', link)
        self.assertNotIn('<QRCodeSVG value={appDelivery', link)
        self.assertIn('/customer/subscriptions/{subscription_id}/app-delivery', ROUTES.read_text(encoding="utf-8"))
        self.assertIn("getAppAccess(appOwner,subscriptionId)", link)
        self.assertIn("appearanceApi.save(role,appearance,resellerId)", delivery)
        self.assertIn("registerAppDirectory(appOrigin.trim())", LICENSE.read_text(encoding="utf-8"))
        self.assertIn('routeKey==="admin/smart-app"', ROUTER_UI.read_text(encoding="utf-8"))
        self.assertIn('routeKey==="reseller/smart-app"', ROUTER_UI.read_text(encoding="utf-8"))
        self.assertIn("/v1/central-app/admin/register", api)
        self.assertIn('@router.post("/admin/register")', DIRECTORY.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
