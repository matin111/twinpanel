"""Regression: Telegram link/account navigation must support QR photo callbacks.

Static handler checks complement existing runtime tests. No Telegram API calls.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def handler(path: str, name: str) -> str:
    content = (ROOT / path).read_text(encoding="utf-8")
    node = next(
        item for item in ast.walk(ast.parse(content))
        if isinstance(item, ast.AsyncFunctionDef) and item.name == name
    )
    return ast.get_source_segment(content, node)


class TelegramLinkPhotoNavigationTests(unittest.TestCase):
    def test_link_recovery_button_from_qr_photo(self):
        body = handler("backend/app/telegram_account_link_bot_original.py",
                       "account_link_start_inline")
        self.assertIn("show_navigation_page(callback.message", body)
        self.assertNotIn("callback.message.edit_text(", body)
        self.assertIn("AccountLinkState.username", body)

    def test_import_link_button_from_qr_photo(self):
        body = handler("backend/app/telegram_subscription_import_bot_v1.py",
                       "import_start")
        self.assertIn("show_navigation_page(callback.message", body)
        self.assertNotIn("callback.message.edit_text(", body)
        self.assertIn("ImportLinkState.link", body)

    def test_account_navigation_buttons_from_qr_photo(self):
        names = ("main_dashboard_inline", "main_account_inline",
                 "main_connect_account_inline")
        for name in names:
            with self.subTest(name=name):
                body = handler("backend/app/telegram_account_link_bot_original.py", name)
                self.assertIn("show_navigation_page(callback.message", body)
                self.assertNotIn("callback.message.edit_text(", body)

    def test_cancel_uses_fresh_message_for_reply_keyboard(self):
        body = handler("backend/app/telegram_account_link_bot_original.py",
                       "account_link_cancel_inline")
        self.assertIn("callback.message.answer(", body)
        self.assertIn("main_runtime.main_keyboard()", body)
        self.assertNotIn("callback.message.edit_text(", body)

    def test_existing_navigation_utility_handles_photo(self):
        src = (ROOT / "backend/app/telegram_navigation_v1.py").read_text()
        self.assertIn('getattr(message, "photo", None)', src)
        self.assertIn("return await message.answer(text, reply_markup=reply_markup)", src)


if __name__ == "__main__":
    unittest.main()
