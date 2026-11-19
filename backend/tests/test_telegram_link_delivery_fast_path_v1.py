"""Run without a database to verify fast Telegram link delivery and its auth."""
import ast
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT / "backend/app/routers/account_delivery.py"
BOT = ROOT / "backend/app/telegram_runtime_bot.py"
QR = ROOT / "backend/app/telegram_subscription_qr_v1.py"
CHART = ROOT / "components/sales-analytics-runtime.tsx"


class FakeHttpException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail


class FakeSession:
    def __init__(self, subscription):
        self.subscription = subscription
        self.lookups = 0

    def get(self, model, subscription_id):
        self.lookups += 1
        return self.subscription if subscription_id == 42 else None

    def query(self, *args):
        raise AssertionError("Fast link delivery must not load protocol credentials or nodes")


def load_endpoint():
    source = ast.parse(DELIVERY.read_text(encoding="utf-8"))
    fn = next(node for node in source.body if isinstance(node, ast.FunctionDef)
              and node.name == "customer_link_delivery")
    fn.decorator_list = []
    called_share = []

    def share_url(db, sub):
        called_share.append(sub)
        return "https://example.com/v1/connect/unchanged-token"

    namespace = {
        "User": object, "Session": object, "Subscription": object,
        "Depends": lambda _value: None, "get_current_user": object(), "get_db": object(),
        "HTTPException": FakeHttpException, "datetime": datetime,
        "_share_url": share_url,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(DELIVERY), "exec"), namespace)
    return namespace["customer_link_delivery"], called_share


class TelegramLinkFastPathTests(unittest.TestCase):
    def setUp(self):
        self.endpoint, self.share_calls = load_endpoint()
        self.user = SimpleNamespace(id=7)
        self.subscription = SimpleNamespace(
            id=42, user_id=7, status=SimpleNamespace(value="active"),
            expires_at=datetime.utcnow()+timedelta(days=2),
            account_username="same-account-name",
        )
        self.db = FakeSession(self.subscription)

    def test_active_owner_receives_only_link_and_username(self):
        result = self.endpoint(42, self.user, self.db)
        self.assertEqual(result, {
            "subscription_link": "https://example.com/v1/connect/unchanged-token",
            "account_username": "same-account-name",
        })
        self.assertEqual(self.db.lookups, 1)
        self.assertEqual(self.share_calls, [self.subscription])

    def test_cannot_read_someone_elses_link(self):
        self.subscription.user_id = 900
        with self.assertRaises(FakeHttpException) as err:
            self.endpoint(42, self.user, self.db)
        self.assertEqual(err.exception.status_code, 404)
        self.assertEqual(self.share_calls, [])

    def test_inactive_and_expired_subscriptions_denied(self):
        self.subscription.status.value = "suspended"
        with self.assertRaises(FakeHttpException) as err:
            self.endpoint(42, self.user, self.db)
        self.assertEqual(err.exception.status_code, 403)
        self.subscription.status.value = "active"
        self.subscription.expires_at = datetime.utcnow()-timedelta(seconds=1)
        with self.assertRaises(FakeHttpException) as err:
            self.endpoint(42, self.user, self.db)
        self.assertEqual(err.exception.status_code, 403)
        self.assertEqual(self.share_calls, [])

    def test_unknown_subscription_denied(self):
        with self.assertRaises(FakeHttpException) as err:
            self.endpoint(99, self.user, self.db)
        self.assertEqual(err.exception.status_code, 404)

    def test_bot_keeps_qr_and_app_credentials_without_heavy_endpoint(self):
        source = ast.parse(BOT.read_text(encoding="utf-8"))
        handler = next(node for node in ast.walk(source) if isinstance(node, ast.AsyncFunctionDef)
                       and node.name == "subscription_connection")
        code = ast.unparse(handler)
        self.assertIn("link-delivery", code)
        self.assertNotIn("connection-info", code)
        self.assertIn("app-delivery", code)
        self.assertIn("send_subscription_link_and_qr", code)
        qr = QR.read_text(encoding="utf-8")
        self.assertIn("await asyncio.to_thread(subscription_qr_photo, value)", qr)
        self.assertIn("message.answer_photo(", qr)

    def test_sales_tooltip_follows_theme_and_is_not_clipped_at_top(self):
        chart = CHART.read_text(encoding="utf-8")
        self.assertIn(':global(html[data-theme="light"]) .sales-tooltip', chart)
        self.assertIn('.sales-tooltip.below{transform:translate(-50%,10px)}', chart)
        self.assertIn('activePoint.y/chart.height<0.47', chart)


if __name__ == "__main__":
    unittest.main()
