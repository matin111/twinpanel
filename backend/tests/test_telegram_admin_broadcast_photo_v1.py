"""Regression coverage for Telegram admin broadcast photos and text."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aiogram import Router
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from app import telegram_admin_ops_v1 as bot
from app.routers import telegram_admin_ops_v1 as api


class FakeClient:
    def __init__(self, status=200):
        self.calls = []
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def post(self, url, json):
        self.calls.append((url, json.copy()))
        return SimpleNamespace(status_code=self.status, json=lambda: {"ok": self.status == 200})


class FakeTelegramMessage:
    def __init__(self, *, photo=None, text=None, caption=None, telegram_id=123):
        self.chat = SimpleNamespace(type="private")
        self.from_user = SimpleNamespace(id=telegram_id)
        self.photo = [SimpleNamespace(file_id=photo)] if photo else []
        self.text = text
        self.caption = caption
        self.answers = []
        self.photos_sent = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))

    async def answer_photo(self, photo, caption=None, **kwargs):
        self.photos_sent.append((photo, caption, kwargs))


class FakeState:
    def __init__(self):
        self.cleared = False

    async def clear(self):
        self.cleared = True


class BroadcastPhotoTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        api._broadcast_drafts.clear()
        self.db = object()

    def tearDown(self):
        api._broadcast_drafts.clear()

    def preview(self, *, text="", photo=None):
        with (
            patch.object(api, "_admin", return_value=SimpleNamespace(id=91)),
            patch.object(api, "_broadcast_target_ids", return_value=[111, 222]),
        ):
            return api.broadcast_preview(
                api.BroadcastDraftIn(
                    telegram_id=123, text=text, photo_file_id=photo,
                ), self.db,
            )

    def test_photo_without_caption_preview(self):
        response = self.preview(photo="AgACAgQAAxkBAabcdef0123456789")
        draft = api._broadcast_drafts[response["nonce"]]
        self.assertTrue(response["has_photo"])
        self.assertEqual(response["total"], 2)
        self.assertEqual(draft["text"], "")
        self.assertEqual(draft["photo_file_id"], "AgACAgQAAxkBAabcdef0123456789")

    def test_photo_with_caption_preview(self):
        response = self.preview(photo="AgACAgQAAxkBAabcdef0123456789", text="تخفیف ویژه")
        self.assertEqual(response["preview"], "تخفیف ویژه")

    def test_text_only_still_supported(self):
        response = self.preview(text="اطلاعیه مهم")
        self.assertFalse(response["has_photo"])
        self.assertIsNone(api._broadcast_drafts[response["nonce"]]["photo_file_id"])

    def test_empty_media_and_text_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            self.preview()
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(api._broadcast_drafts, {})

    def test_oversized_photo_caption_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            self.preview(text="x" * 1025, photo="valid_photo_file_id")
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(api._broadcast_drafts, {})

    def test_plain_text_length_limit_unchanged(self):
        with self.assertRaises(ValidationError):
            api.BroadcastDraftIn(telegram_id=123, text="x" * 4001)

    async def test_confirmation_schedules_one_photo_job_and_nonce_consumed(self):
        preview = self.preview(text="خبر خوب", photo="photo_file_id_123456789")
        tasks = BackgroundTasks()
        with (
            patch.object(api, "_admin", return_value=SimpleNamespace(id=91)),
            patch.object(api, "_broadcast_target_ids", return_value=[111, 222]),
        ):
            result = await api.broadcast_send(
                api.BroadcastConfirmIn(telegram_id=123, nonce=preview["nonce"]),
                tasks, self.db,
            )
            self.assertEqual(result["queued"], 2)
            self.assertEqual(len(tasks.tasks), 1)
            self.assertIs(tasks.tasks[0].func, api._deliver_broadcast)
            self.assertEqual(tasks.tasks[0].args,
                             ("خبر خوب", [111, 222], 123, "photo_file_id_123456789"))
            with self.assertRaises(HTTPException) as raised:
                await api.broadcast_send(
                    api.BroadcastConfirmIn(telegram_id=123, nonce=preview["nonce"]),
                    BackgroundTasks(), self.db,
                )
            self.assertEqual(raised.exception.status_code, 409)

    async def test_photo_delivered_via_sendphoto_once_per_recipient(self):
        fake = FakeClient()
        with (
            patch.object(api, "load_bot_token", return_value="TEST-TOKEN"),
            patch.object(api.httpx, "AsyncClient", return_value=fake),
            patch.object(api.asyncio, "sleep", return_value=None) as mock_sleep,
        ):
            # Do not actually send to Telegram.
            await api._deliver_broadcast("سلام", [111, 222], 123, "file_id_123456")
        self.assertEqual(len(fake.calls), 3)  # two photo sends + text report
        for url, body in fake.calls[:2]:
            self.assertTrue(url.endswith("/sendPhoto"))
            self.assertEqual(body["photo"], "file_id_123456")
            self.assertEqual(body["caption"], "سلام")
            self.assertNotIn("text", body)
        self.assertTrue(fake.calls[2][0].endswith("/sendMessage"))
        self.assertEqual(fake.calls[2][1]["chat_id"], 123)

    async def test_text_delivered_via_sendmessage_as_before(self):
        fake = FakeClient()
        with (
            patch.object(api, "load_bot_token", return_value="TEST-TOKEN"),
            patch.object(api.httpx, "AsyncClient", return_value=fake),
            patch.object(api.asyncio, "sleep", return_value=None),
        ):
            await api._deliver_broadcast("اطلاعیه", [111], 123)
        self.assertEqual(fake.calls[0][1]["text"], "اطلاعیه")
        self.assertTrue(fake.calls[0][0].endswith("/sendMessage"))
        self.assertNotIn("photo", fake.calls[0][1])

    async def test_bot_draft_uses_photo_file_id_and_shows_preview(self):
        async def request_fn(method, path, **kwargs):
            if path.endswith("/me/123"):
                return {"ok": True}
            if path.endswith("/broadcast/preview"):
                self.assertEqual(method, "POST")
                self.assertEqual(kwargs["payload"]["photo_file_id"], "photo_1234567")
                self.assertEqual(kwargs["payload"]["text"], "تیتر")
                return {"nonce": "abcdef1234567890", "total": 13, "preview": "تیتر"}
            raise AssertionError(path)

        router = Router()
        bot.install_telegram_admin_ops(router, request_fn)
        draft_handler = next(
            h.callback for h in router.message.handlers
            if h.callback.__name__ == "broadcast_draft"
        )
        message = FakeTelegramMessage(photo="photo_1234567", caption="تیتر")
        state = FakeState()
        await draft_handler(message, state)
        self.assertTrue(state.cleared)
        self.assertEqual(message.photos_sent[0][0], "photo_1234567")
        self.assertIn("13", message.answers[-1][0])
        self.assertEqual(
            message.answers[-1][1]["reply_markup"].inline_keyboard[0][0].callback_data,
            "adm:bcast:abcdef1234567890",
        )

    async def test_bot_rejects_unsupported_media_without_creating_draft(self):
        called = False
        async def request_fn(*args, **kwargs):
            nonlocal called
            if args[1].endswith("/me/123"):
                return {"ok": True}
            called = True
            raise AssertionError("Unexpected broadcast preview")
        router = Router()
        bot.install_telegram_admin_ops(router, request_fn)
        handler = next(
            h.callback for h in router.message.handlers
            if h.callback.__name__ == "broadcast_draft"
        )
        message = FakeTelegramMessage()
        state = FakeState()
        await handler(message, state)
        self.assertFalse(called)
        self.assertFalse(state.cleared)
        self.assertIn("متن پیام نامعتبر", message.answers[-1][0])


if __name__ == "__main__":
    unittest.main()
