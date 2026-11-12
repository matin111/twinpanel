"""Regression tests for Buy Account action under Telegram broadcasts."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routers import telegram_admin_ops_v1 as api
from app.telegram_purchase_bot import create_purchase_router


class FakeClient:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, json):
        self.calls.append((url, dict(json)))
        return SimpleNamespace(status_code=200, json=lambda: {"ok": True})


class BroadcastButtonTests(unittest.IsolatedAsyncioTestCase):
    async def _deliver(self, text, photo=None):
        fake = FakeClient()
        with (
            patch.object(api, "load_bot_token", return_value="UNIT-TEST"),
            patch.object(api.httpx, "AsyncClient", return_value=fake),
            patch.object(api.asyncio, "sleep", return_value=None),
        ):
            await api._deliver_broadcast(text, [111, 222], 999, photo)
        return fake.calls

    async def test_text_broadcast_has_one_buy_button_per_user(self):
        calls = await self._deliver("پیام همگانی")
        self.assertEqual(len(calls), 3)
        for url, data in calls[:2]:
            self.assertTrue(url.endswith("/sendMessage"))
            self.assertEqual(data["text"], "پیام همگانی")
            self.assertEqual(data["reply_markup"], {
                "inline_keyboard": [[
                    {"text": "🛒 خرید اکانت", "callback_data": "shop:broadcast"}
                ]]
            })
        self.assertNotIn("reply_markup", calls[2][1])

    async def test_photo_with_caption_has_button_and_preserves_media(self):
        calls = await self._deliver("کپشن", photo="FILE_ID_VALID_123")
        for url, data in calls[:2]:
            self.assertTrue(url.endswith("/sendPhoto"))
            self.assertEqual(data["photo"], "FILE_ID_VALID_123")
            self.assertEqual(data["caption"], "کپشن")
            self.assertEqual(
                data["reply_markup"]["inline_keyboard"][0][0]["callback_data"],
                "shop:broadcast",
            )

    async def test_photo_without_caption_has_buy_button(self):
        calls = await self._deliver("", photo="FILE_ID_VALID_123")
        for _, data in calls[:2]:
            self.assertEqual(data["photo"], "FILE_ID_VALID_123")
            self.assertNotIn("caption", data)
            self.assertEqual(
                data["reply_markup"]["inline_keyboard"][0][0]["text"],
                "🛒 خرید اکانت",
            )

    async def test_callback_opens_new_menu_without_editing_announcement(self):
        requested = []
        async def request_fn(method, path, **_kwargs):
            requested.append((method, path))
            if path == "/v1/plans":
                return [{"id": 301, "is_active": True,
                         "name": "اقتصادی 30", "price_toman": 30000,
                         "duration_days": 30, "traffic_gb": 30,
                         "subscription_type": "اقتصادی", "device_limit": 1}]
            raise AssertionError(path)

        async def session_fn(_telegram_id):
            return {"access_token": "test-access-token"}

        router = create_purchase_router(request_fn, session_fn)
        handlers = [item.callback for item in router.observers["callback_query"].handlers
                    if item.callback.__name__ == "shop_from_broadcast"]
        self.assertEqual(len(handlers), 1)

        class FakeMessage:
            def __init__(self):
                self.sent = []
                self.edited = []

            async def answer(self, text, **kwargs):
                self.sent.append((text, kwargs))

            async def edit_text(self, text, **kwargs):
                self.edited.append((text, kwargs))
                raise AssertionError("The original broadcast must not be edited")

        class FakeCallback:
            def __init__(self):
                self.from_user = SimpleNamespace(id=111)
                self.message = FakeMessage()
                self.acks = 0

            async def answer(self, **_kwargs):
                self.acks += 1

        class FakeState:
            def __init__(self):
                self.cleared = False

            async def clear(self):
                self.cleared = True

        callback, state = FakeCallback(), FakeState()
        await handlers[0](callback, state)
        self.assertEqual(callback.acks, 1)
        self.assertTrue(state.cleared)
        self.assertFalse(callback.message.edited)
        self.assertEqual(len(callback.message.sent), 1)
        self.assertIn("خرید اشتراک", callback.message.sent[0][0])
        markup = callback.message.sent[0][1]["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "shop:type:0")
        self.assertEqual(requested, [("GET", "/v1/plans")])


if __name__ == "__main__":
    unittest.main()
