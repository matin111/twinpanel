"""Guard legacy reseller-bot link retrieval against TwinConnect auth coupling."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
BOT = ROOT / "backend/app/reseller_bot_subscription_link_runtime.py"


class UsernameOnlyLinkRegression(unittest.TestCase):
    def test_link_lookup_does_not_require_app_auth_or_app_credentials(self):
        source = BOT.read_text(encoding="utf-8")
        self.assertIn("class ResellerSubscriptionLinkState(StatesGroup):", source)
        self.assertIn("username = State()", source)
        self.assertIn("_owned_subscription_by_username(", source)
        self.assertIn("_share_url(db, sub)", source)
        self.assertNotIn("app_delivery_payload", source)
        self.assertNotIn("central_app_credentials", source)
        self.assertNotIn("app_password", source)
        self.assertNotIn("authenticate_app", source)
        self.assertNotIn("password = State()", source)

    def test_public_link_delivery_keeps_previous_format(self):
        source = BOT.read_text(encoding="utf-8")
        self.assertIn('✅ <b>لینک اکانت</b>', source)
        self.assertIn('reply_markup=_link_keyboard(subscription_link)', source)


if __name__ == "__main__":
    unittest.main()
