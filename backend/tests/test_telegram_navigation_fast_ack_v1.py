"""Regression checks for Telegram navigation from QR photos and stale callbacks."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def _function(source, function_name):
    tree = ast.parse(source)
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
        and node.name == function_name
    )


def test_home_callback_is_registered_and_does_not_call_api():
    src = read("backend/app/telegram_runtime_bot.py")
    func = _function(src, "main_home_callback")
    body = ast.get_source_segment(src, func)
    assert '@router.callback_query(F.data == "main:home")' in src
    assert "await callback.answer()" in body
    assert "await state.clear()" in body
    assert "reply_markup=main_keyboard()" in body
    assert "await request(" not in body
    assert "await session(" not in body


def test_account_list_acknowledges_callback_before_any_api_request():
    src = read("backend/app/telegram_runtime_bot.py")
    body = ast.get_source_segment(src, _function(src, "subscriptions_callback"))
    assert body.index("await callback.answer()") < body.index("await _telegram_session_token")
    assert "show_navigation_page(callback.message" in body
    assert "callback.message.edit_text(" not in body


def test_back_from_qr_to_account_management_is_media_safe():
    src = read("backend/app/telegram_subscription_import_bot_v1.py")
    body = ast.get_source_segment(src, _function(src, "import_detail"))
    assert "await callback.answer()" in body
    assert "await show_navigation_page(" in body
    assert "callback.message.edit_text(" not in body


def test_photo_navigation_sends_new_message_instead_of_editing_caption_as_text():
    src = read("backend/app/telegram_navigation_v1.py")
    body = ast.get_source_segment(src, _function(src, "show_navigation_page"))
    assert 'getattr(message, "photo", None)' in body
    assert "return await message.answer(text, reply_markup=reply_markup)" in body
    assert 'message.edit_text(text, reply_markup=reply_markup)' in body
    assert '"message is not modified"' in body


def test_sub_and_qr_callbacks_acknowledge_before_slow_api():
    runtime = read("backend/app/telegram_runtime_bot.py")
    imported = read("backend/app/telegram_subscription_import_bot_v1.py")
    for src, func_name in (
        (runtime, "subscription_detail"),
        (runtime, "subscription_connection"),
        (imported, "import_connection"),
    ):
        body = ast.get_source_segment(src, _function(src, func_name))
        assert body.index("await callback.answer()") < body.index("await _" if func_name == "import_connection" else "try:")
