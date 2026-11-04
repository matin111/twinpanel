"""Smoke: one verified sublink is used in both Telegram QR and caption."""
from __future__ import annotations

import asyncio
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
shared = (APP / "telegram_subscription_qr_v1.py").read_text("utf-8")
owned = (APP / "telegram_runtime_bot.py").read_text("utf-8")
imported = (APP / "telegram_subscription_import_bot_v1.py").read_text("utf-8")

for content in (shared, owned, imported):
    compile(content, "<telegram QR>", "exec")

assert "async def send_subscription_link_and_qr(" in shared
assert "photo=photo" in shared and "caption=caption" in shared
assert "qr.add_data(link)" in shared
assert "escape(value)" in shared
assert "await message.answer_photo(" in shared
assert "await send_subscription_link_and_qr(" in owned
assert "await send_subscription_link_and_qr(" in imported
assert "🔗 ساب‌لینک + QR Code" in owned
assert "🔗 ساب‌لینک + QR Code" in imported
assert "subimp:refresh:" in imported
assert "subimp:renew:" in imported
assert "subimp:ask:password:" in imported

# Functional check: the helper sends exactly one photo with a caption that
# contains the same URL encoded in the QR image; no separate link message.
from aiogram.types import BufferedInputFile
scope = {}
exec(compile(shared, '<combined QR>', 'exec'), scope)
send_subscription_link_and_qr = scope['send_subscription_link_and_qr']

class FakeMessage:
    def __init__(self):
        self.calls = []
    async def answer_photo(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs

url = "https://sub.example.test/v1/connect/user_test-123456"
msg = FakeMessage()
asyncio.run(send_subscription_link_and_qr(msg, url, username="user_test"))
assert len(msg.calls) == 1
call = msg.calls[0]
assert isinstance(call["photo"], BufferedInputFile)
assert len(call["photo"].data) > 500
assert url in call["caption"]
assert "user_test" in call["caption"]
assert not any(k in call for k in ("parse_mode", "protect_content"))
print("TELEGRAM_COMBINED_SUBLINK_QR_V1=PASS")
