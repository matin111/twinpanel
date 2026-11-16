"""Focused, non-network tests for the main Telegram renewal wallet flow."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app import telegram_runtime_bot as bot


class FakeCallback:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=4499)
        self.message = SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock())
        self.answer = AsyncMock()


def callbacks():
    return {entry.callback.__name__: entry.callback
            for entry in bot.router.callback_query.handlers}


class RenewalWalletTest(unittest.IsolatedAsyncioTestCase):
    def test_wallet_is_available_without_external_gateways(self):
        markup = bot.renewal_payment_methods_keyboard(351, [])
        self.assertEqual(
            markup.inline_keyboard[0][0].callback_data,
            "renewwallet:preview:351",
        )

    async def test_preview_and_confirm_both_use_existing_wallet_endpoint(self):
        requests = []

        async def fake_request(method, path, **kwargs):
            requests.append((method, path))
            if path == "/v1/store/orders/me":
                return [{"id": 351, "status": "pending_payment", "amount_toman": 150000}]
            if path == "/v1/wallet/me":
                return {"balance_toman": 200000}
            if path == "/v1/wallet/orders/351/pay":
                return {"ok": True, "order": {"status": "paid"}}
            raise AssertionError(path)

        with patch.object(bot, "request", side_effect=fake_request), \
             patch.object(bot, "_telegram_session_token", new=AsyncMock(return_value="test")):
            cb = FakeCallback("renewwallet:preview:351")
            await callbacks()["renewal_wallet_preview"](cb)
            cb.answer.assert_awaited_once()
            buttons = cb.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
            self.assertEqual(buttons[0][0].callback_data, "renewwallet:confirm:351")

            cb = FakeCallback("renewwallet:confirm:351")
            await callbacks()["renewal_wallet_confirm"](cb)
            cb.answer.assert_awaited_once()
            self.assertIn("رزرو", cb.message.edit_text.await_args.args[0])
            self.assertEqual(
                requests.count(("POST", "/v1/wallet/orders/351/pay")), 1,
            )

    async def test_api_requests_reuse_shared_client_without_new_connection(self):
        calls = []

        def handler(request):
            calls.append(request.url.path)
            return httpx.Response(200, json={"ok": True})

        old = bot._api_client
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        bot._api_client = client
        try:
            await bot.request("GET", "/health")
            await bot.request("GET", "/v1/plans")
            self.assertEqual(calls, ["/health", "/v1/plans"])
        finally:
            bot._api_client = old
            await client.aclose()


if __name__ == "__main__":
    unittest.main()
