"""Ensure receipt photo and status refresh show complete readable purchase details."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "app"
API = ROOT / "routers/telegram_admin_ops_v1.py"
BOT = ROOT / "telegram_admin_ops_v1.py"
PUSH = ROOT / "services/telegram_admin_receipt_push.py"


def get_formatter():
    tree = ast.parse(API.read_text(encoding="utf-8"))
    fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "format_admin_receipt")
    env = {"_RECEIPT_STATUS_FA": {"pending_payment": "در انتظار پرداخت / بررسی", "awaiting_review": "در انتظار بررسی"}}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(API), "exec"), env)
    return env["format_admin_receipt"]


class ReceiptCaptionTests(unittest.TestCase):
    def test_purchase_includes_user_order_plan_payment(self):
        text = get_formatter()("purchase", {
            "id": 477, "user_id": 273, "user_label": "مشتری آزمایشی",
            "telegram_id": 987654321, "order_id": 912,
            "plan_name": "سه ماهه ۵۰ گیگ", "subscription_id": 2150,
            "method": "card_to_card", "status": "pending_payment",
            "amount_toman": 100361, "base_amount_toman": 110000,
            "discount_amount_toman": 9639, "tracking_code": "TX123",
        })
        for expected in ("273", "مشتری آزمایشی", "987654321", "912",
                         "سه ماهه ۵۰ گیگ", "MV-2150", "100,361", "TX123"):
            self.assertIn(expected, text)
        self.assertIn("\n", text)
        self.assertNotIn("\\n", text)
        self.assertLessEqual(len(text), 1024)

    def test_wallet_no_fake_purchase(self):
        text = get_formatter()("wallet", {
            "id": 478, "user_id": 274, "user_label": "کاربر دوم",
            "status": "awaiting_review", "amount_toman": 50000,
            "wallet_credit_toman": 50000, "method": "card_to_card",
        })
        self.assertIn("50,000", text)
        self.assertIn("شارژ کیف پول", text)
        self.assertNotIn("پلن انتخابی", text)

    def test_unsafe_customer_labels_escaped(self):
        text = get_formatter()("purchase", {
            "id": 1, "user_id": 9, "user_label": "<bad&name>",
            "plan_name": "plan <unsafe>", "order_id": 2,
            "status": "awaiting_review", "amount_toman": 10000,
        })
        self.assertIn("&lt;bad&amp;name&gt;", text)
        self.assertIn("plan &lt;unsafe&gt;", text)

    def test_push_and_refresh_use_identical_formatter(self):
        push = PUSH.read_text(encoding="utf-8")
        bot = BOT.read_text(encoding="utf-8")
        self.assertIn("caption = format_admin_receipt(kind, receipt)", push)
        self.assertIn("caption = format_admin_receipt(kind, data)", bot)
        self.assertIn('"parse_mode": "HTML"', push)
        self.assertIn("callback.message.edit_caption(", bot)
        self.assertIn("callback.message.edit_text(", bot)


if __name__ == "__main__":
    unittest.main()
