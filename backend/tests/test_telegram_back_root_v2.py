"""Regression for the Telegram root-shop Back button and photo QR navigation."""
import ast
from html import unescape
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]


def source(path):
    return (BASE / path).read_text(encoding="utf-8")


def test_auto_back_on_first_purchase_screen_goes_home_not_same_page():
    src = source("backend/app/bot_text_middleware.py")
    tree = ast.parse(src)
    middleware = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BotTextRequestMiddleware")
    fn = next(n for n in middleware.body if isinstance(n, ast.FunctionDef) and n.name == "_navigation_back")
    function_source = ast.get_source_segment(src, fn)
    # Run the self-contained static helper without connecting to the database.
    ns = {"unescape": unescape}
    exec(function_source.replace("@staticmethod\n", ""), ns)
    back = ns["_navigation_back"]
    assert back("🛒 خرید اشتراک\n\nابتدا نوع اشتراک را انتخاب کنید:", "admin") == "main:home"
    assert back("اشتراک عمومی\nتعداد کاربر را انتخاب کنید:", "admin") == "shop:list"
    assert back("🛒 خرید اشتراک\n\nابتدا تعداد کاربری را انتخاب کنید:", "admin") == "main:home"


def test_qr_explicit_management_back_prevents_wrong_generated_back():
    src = source("backend/app/bot_text_middleware.py")
    assert 'label.lstrip().startswith(("⬅️ مدیریت", "↩️ مدیریت", "⬅️ اکانت‌های من"))' in src


def test_shop_list_acknowledges_immediately_and_can_handle_idempotent_edit():
    src = source("backend/app/telegram_purchase_bot.py")
    tree = ast.parse(src)
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "shop_list")
    body = ast.get_source_segment(src, handler)
    assert body.index("await acknowledge_navigation(callback)") < body.index("await user_token(")
    assert 'await show_navigation_page(callback.message,' in body
    assert "callback.message.edit_text(" not in body


def test_safe_navigation_discards_telegram_same_message_error():
    src = source("backend/app/telegram_navigation_v1.py")
    assert '"message is not modified" in detail' in src
    assert "return await message.answer(text, reply_markup=reply_markup)" in src
