import asyncio

from app.telegram_expiry_notification_ui_v1 import _ExpiryAwareBotProxy, _expiry_keyboard


def test_expiry_keyboard_has_renew_back_and_home_actions():
    keyboard = _expiry_keyboard(2170)
    rows = keyboard.inline_keyboard

    assert rows[0][0].text == "💳 تمدید اشتراک"
    assert rows[0][0].callback_data == "subrenew:2170"
    assert rows[0][0].style == "primary"

    assert rows[1][0].text == "⬅️ بازگشت"
    assert rows[1][0].callback_data == "subs:list"
    assert rows[1][1].text == "🏠 منوی اصلی"
    assert rows[1][1].callback_data == "main:home"
    assert rows[1][1].style is None


def test_expiry_proxy_injects_keyboard_for_expiry_notification():
    class FakeBot:
        def __init__(self):
            self.kwargs = None

        async def send_message(self, *args, **kwargs):
            self.kwargs = kwargs
            return True

    async def run():
        bot = FakeBot()
        proxy = _ExpiryAwareBotProxy(bot)
        await proxy.send_message(
            chat_id=123,
            text="🔔 <b>اشتراک شما به‌زودی منقضی می‌شود</b>\n\nاشتراک شماره 2170",
        )
        return bot.kwargs

    kwargs = asyncio.run(run())
    keyboard = kwargs["reply_markup"]

    assert keyboard.inline_keyboard[0][0].callback_data == "subrenew:2170"
    assert keyboard.inline_keyboard[1][0].callback_data == "subs:list"
    assert keyboard.inline_keyboard[1][1].callback_data == "main:home"
