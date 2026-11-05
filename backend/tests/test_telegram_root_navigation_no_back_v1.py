"""Regression checks for root Telegram pages with no meaningful Back parent."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def function(source, name):
    return next(node for node in ast.walk(ast.parse(source))
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name)


def test_global_middleware_never_invents_a_back_callback():
    s = read("backend/app/bot_text_middleware.py")
    fn = ast.get_source_segment(s, function(s, "_add_navigation"))
    assert "callback_data=back" not in fn
    assert "↩️ برگشت" not in fn
    assert "self._navigation_back(" not in fn
    assert 'callback_data=home' in fn
    assert "InlineKeyboardMarkup(inline_keyboard=rows)" in fn


def test_subscription_and_wallet_root_pages_keep_only_real_actions():
    subs = read("backend/app/telegram_runtime_bot.py")
    wallet = read("backend/app/telegram_wallet_bot.py")
    assert 'subscription_list_keyboard(' in subs
    assert 'callback_data="wallet:refresh"' in wallet
    assert 'callback_data="wallet:topup"' in wallet
    assert 'callback_data="wallet:transactions"' in wallet


def test_wallet_refresh_acknowledges_early_and_uses_safe_idempotent_edit():
    s = read("backend/app/telegram_wallet_bot.py")
    refresher = ast.get_source_segment(s, function(s, "wallet_refresh"))
    sender = ast.get_source_segment(s, function(s, "send_wallet"))
    assert refresher.index("await acknowledge_navigation(callback)") < refresher.index("await send_wallet(")
    assert "await callback.answer(str(exc)" not in refresher
    assert "await show_navigation_page(target, text, reply_markup=wallet_keyboard())" in sender
    assert "await target.edit_text(" not in sender


def test_nested_keyboard_back_buttons_are_preserved():
    purchase = read("backend/app/telegram_purchase_bot.py")
    wallet = read("backend/app/telegram_wallet_bot.py")
    assert 'text="⬅️ بازگشت به دسته‌بندی‌ها"' in purchase
    assert 'text="↩️ بازگشت به نوع اشتراک"' in purchase
    assert 'text="⬅️ بازگشت", callback_data="wallet:refresh"' in wallet
