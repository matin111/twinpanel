"""Regression: app-only identities must never alter VPN credentials or links."""
import ast
import asyncio
from html import escape
import re
import secrets
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "backend/app/central_app_credentials.py"
MODELS = ROOT / "backend/app/central_app_credential_models.py"
ROUTES = ROOT / "backend/app/routers/central_app_credentials_v1.py"
FACTORY = ROOT / "backend/app/services/subscription_factory.py"
MAIN = ROOT / "backend/app/main.py"
BOT = ROOT / "backend/app/routers/reseller_bot_delivery_runtime_v2.py"
BOT_LINK = ROOT / "backend/app/reseller_bot_subscription_link_runtime.py"
MAIN_BOT = ROOT / "backend/app/telegram_runtime_bot.py"
QR = ROOT / "backend/app/telegram_subscription_qr_v1.py"
FLUTTER = ROOT / "clients/twinconnect/lib/main.dart"
CLIENT = ROOT / "clients/twinconnect/lib/tenant_api.dart"


def _exec_selected(*names):
    tree = ast.parse(CORE.read_text(encoding="utf-8"))
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in names]
    scope = {
        "secrets": secrets,
        "installation_namespace": lambda _: "TP0123456789ABCDEF",
        "reseller_prefix": lambda _, ident: f"TP0123456789ABCDEF_R{ident:X}_",
        "ensure_installation_id": lambda: "local-test",
    }
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(CORE), "exec"), scope)
    return scope


class SeparateAppCredentialContract(unittest.TestCase):
    def test_generated_credentials_are_unique_and_follow_vendor_prefix(self):
        scope = _exec_selected("_username", "_password")
        owner = scope["_username"](0)
        reseller = scope["_username"](24)
        self.assertRegex(owner, r"^TP[0-9A-F]{16}_A_APP[0-9A-F]{16}$")
        self.assertRegex(reseller, r"^TP[0-9A-F]{16}_R18_APP[0-9A-F]{16}$")
        self.assertNotEqual(owner, scope["_username"](0))
        self.assertNotEqual(owner, reseller)
        first, second = scope["_password"](), scope["_password"]()
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 24)

    def test_password_is_independent_of_vpn_and_stored_protected(self):
        source = CORE.read_text()
        factory = FACTORY.read_text()
        models = MODELS.read_text()
        self.assertIn('"subscription_app_credentials"', models)
        self.assertIn("password_hash", models)
        self.assertIn("delivery_password_encrypted", models)
        self.assertIn("hash_password(password)", source)
        self.assertIn("_fernet().encrypt(", source)
        self.assertIn("_fernet().decrypt(", source)
        self.assertIn("verify_password(password, row.password_hash)", source)
        self.assertIn("row.revision += 1", source)
        self.assertIn("get_or_issue_app_credentials(db, sub, reseller_id=reseller_id or 0)", factory)
        self.assertIn("sub.account_password_encrypted = password", factory)
        rotator = source.split("def rotate_app_credentials(", 1)[1].split(
            "def authenticate_app(", 1)[0]
        self.assertNotIn("account_password_encrypted", rotator)
        self.assertNotIn("share_code", rotator)

    def test_public_app_login_returns_session_not_vpn_password_or_link(self):
        api = ROUTES.read_text()
        login = api.split('@router.post("/public/login")', 1)[1].split(
            '@router.get("/session/brand")', 1)[0]
        self.assertIn("authenticate_app(db, payload.username, payload.password)", login)
        self.assertIn('"session_token": token', login)
        self.assertIn('"brand": brand', login)
        self.assertNotIn('"app_password"', login)
        self.assertNotIn('"subscription_link"', login)
        self.assertIn("verify_app_session(db, authorization[7:].strip())", api)
        self.assertIn('"Referrer-Policy": "no-referrer"', api)
        self.assertIn('"Cache-Control": "private, no-store, max-age=0"', api)

    def test_admin_and_reseller_delivery_cannot_access_cross_reseller(self):
        source = ROUTES.read_text()
        self.assertIn("_=Depends(require_admin)", source)
        self.assertIn("reseller: Reseller = Depends(require_reseller)", source)
        self.assertIn("ResellerSubscription.reseller_id == int(reseller_id)", source)
        self.assertIn("return _deliver(db, _owner_delivery(", source)
        self.assertIn('"app_username": creds["username"]', source)
        self.assertIn('"app_password": creds["password"]', source)
        self.assertIn('"subscription_link": _share_url(db, sub)', source)
        self.assertIn("vpn_credentials_unchanged", source)
        self.assertIn("central_app_credential_models", MAIN.read_text())

    def test_bot_sends_app_login_only_to_verified_buyer(self):
        bot = BOT.read_text()
        self.assertIn("int(order.telegram_id) == int(telegram_id)", bot)
        self.assertIn("ResellerSubscription.reseller_id == int(reseller_id)", bot)
        self.assertIn("app_delivery_payload(db, sub)", bot)
        self.assertIn("نام کاربری مخصوص اپ", bot)
        self.assertIn("رمز مخصوص اپ", bot)
        owned = BOT_LINK.read_text()
        self.assertIn("_owned_subscription_by_username(", owned)
        self.assertIn("linked_user(", owned)
        self.assertIn("app_delivery_payload(db, sub)", owned)

    def test_main_bot_delivery_is_authenticated_and_owner_scoped(self):
        api = ROUTES.read_text(encoding="utf-8")
        section = api.split(
            '@router.post("/customer/subscriptions/{subscription_id}/app-delivery")', 1
        )[1].split(
            '@router.post("/reseller/subscriptions/{subscription_id}/app-delivery")', 1
        )[0]
        self.assertIn("user: User = Depends(get_current_user)", section)
        self.assertIn("int(sub.user_id) != int(user.id)", section)
        self.assertIn("raise HTTPException(status_code=404", section)
        self.assertIn("return _deliver(db, sub, reset=False)", section)

        bot = MAIN_BOT.read_text(encoding="utf-8")
        qr = QR.read_text(encoding="utf-8")
        self.assertIn("int(owned.user_id) == int(row.user_id)", bot)
        self.assertIn("app_delivery_payload(db, owned)", bot)
        self.assertIn("نام کاربری مخصوص اپ:", bot)
        self.assertIn("رمز مخصوص اپ:", bot)
        self.assertIn("customer/subscriptions/{sub_id}/app-delivery", bot)
        self.assertIn("app_credentials=app_credentials", bot)
        self.assertIn("len(text) <= 1024", bot)
        self.assertIn("subscription_qr_photo(value)", qr)
        self.assertIn("app_credentials: dict | None = None", qr)
        self.assertIn("if app_credentials:", qr)
        self.assertIn('f"<code>{escape(value)}</code>', qr)
        self.assertIn("escape(str(app_credentials.get(\"app_password\")", qr)

    def test_qr_message_keeps_link_and_app_password_separate_and_escaped(self):
        # Run the actual async caption builder with a fake Telegram transport;
        # no customer credential is sent over the network during this test.
        source = QR.read_text(encoding="utf-8")
        tree = ast.parse(source)
        target = next(node for node in tree.body
                      if isinstance(node, ast.AsyncFunctionDef)
                      and node.name == "send_subscription_link_and_qr")
        scope = {"subscription_qr_photo": lambda url: "mock-qr", "escape": escape}
        exec(compile(ast.Module(body=[target], type_ignores=[]),
                     str(QR), "exec"), scope)

        class FakeMessage:
            def __init__(self):
                self.output = None

            async def answer_photo(self, **kwargs):
                self.output = kwargs
                return kwargs

        msg = FakeMessage()
        value = "https://panel.example.org/v1/connect/random-token"
        result = asyncio.run(scope["send_subscription_link_and_qr"](
            msg, value, username="VPN_A", app_credentials={
                "app_username": "APP_<USER>",
                "app_password": "P&<SECRET>",
            },
        ))
        caption = result["caption"]
        self.assertEqual(result["photo"], "mock-qr")
        self.assertIn(f"<code>{value}</code>", caption)
        self.assertIn("APP_&lt;USER&gt;", caption)
        self.assertIn("P&amp;&lt;SECRET&gt;", caption)
        self.assertIn("رمز اپ:", caption)
        self.assertLessEqual(len(caption), 1024)

    def test_client_only_has_username_and_app_password_fields(self):
        flutter = FLUTTER.read_text()
        client = CLIENT.read_text()
        self.assertIn("Key('accountUsername')", flutter)
        self.assertIn("Key('appPassword')", flutter)
        self.assertIn("obscureText: true", flutter)
        for removed in ("Key('subscriptionLink')", "Key('tenantCode')",
                        "Key('windowsDemoButton')", "strings.appHeadline"):
            self.assertNotIn(removed, flutter)
        self.assertIn("final namespace = TenantIdentity.parseNamespace(username, '');", flutter)
        self.assertIn("await api.login(", flutter)
        self.assertIn("sessionToken: loggedIn.sessionToken", flutter)
        self.assertIn("'/v1/central-app/public/login'", client)
        self.assertIn("'/v1/central-app/session/protocols'", client)


if __name__ == "__main__":
    unittest.main()
