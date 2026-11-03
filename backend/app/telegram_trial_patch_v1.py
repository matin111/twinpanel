from __future__ import annotations

from html import escape
from typing import Any

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


_INSTALLED = False
TRIAL_LABEL = "🎁 اکانت تست"


def _delivery_link(result: dict[str, Any]) -> str:
    delivery = result.get("delivery") or {}
    return str(
        delivery.get("subscription_link")
        or delivery.get("share_url")
        or result.get("subscription_link")
        or ""
    ).strip()


def _friendly_trial_error(exc: Exception) -> tuple[str, bool]:
    detail = getattr(exc, "detail", str(exc))
    code = ""
    message = ""

    if isinstance(detail, dict):
        code = str(detail.get("code") or "").strip()
        message = str(detail.get("message") or "").strip()
    else:
        text = str(detail or "").strip()
        code = text
        message = text

    if (
        "main_trial_already_claimed" in code
        or "reseller_trial_already_claimed" in code
        or "main_trial_already_claimed" in message
        or "reseller_trial_already_claimed" in message
    ):
        return (
            "🎁 <b>اکانت تست قبلاً دریافت شده</b>\n\n"
            "شما قبلاً از اکانت تست رایگان استفاده کرده‌اید.\n"
            "برای مشاهده اطلاعات اتصال، از بخش «اشتراک‌های من» استفاده کنید.",
            True,
        )

    if message:
        return "❌ " + escape(message), False

    return "❌ خطا در دریافت اکانت تست. لطفاً دوباره تلاش کنید.", False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import reseller_bot_runtime, telegram_purchase_bot

    original_create_purchase_router = telegram_purchase_bot.create_purchase_router
    original_reseller_keyboard = reseller_bot_runtime._main_keyboard
    original_reseller_build_router = reseller_bot_runtime.build_router

    def create_purchase_router_with_trial(request_fn, session_fn):
        router = original_create_purchase_router(request_fn, session_fn)

        async def claim_main_bot_trial(callback):
            # Provisioning can take longer than Telegram's callback-query TTL.
            # Acknowledge immediately and send the final result as a normal message.
            await callback.answer("در حال ساخت اکانت تست…")
            try:
                session = await session_fn(callback.from_user.id)
                token = session["access_token"]
                result = await request_fn(
                    "POST",
                    "/v1/trial/claim",
                    token=token,
                    payload={},
                )
            except Exception as exc:
                text, already_claimed = _friendly_trial_error(exc)
                markup = None
                if already_claimed:
                    markup = InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(
                                text="📦 مشاهده اشتراک‌های من",
                                callback_data="subs:list",
                            )
                        ]]
                    )
                await callback.message.answer(text, reply_markup=markup)
                return

            link = _delivery_link(result)
            sub_id = int(result.get("subscription_id") or 0)
            lines = [
                "🎁 <b>اکانت تست شما فعال شد</b>",
                "",
                f"📅 اعتبار: <b>{int(result.get('duration_days') or 1)} روز</b>",
                f"📦 حجم: <b>{int(result.get('traffic_mb') or 500)} MB</b>",
            ]
            if sub_id:
                lines.append(f"🆔 اشتراک: <code>#{sub_id}</code>")
            if link:
                lines.extend(["", "🔗 <b>لینک اتصال:</b>", f"<code>{escape(link)}</code>"])
            await callback.message.edit_text(
                "\n".join(lines),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(text="📦 اشتراک‌های من", callback_data="subs:list")
                    ]]
                ),
            )

        router.callback_query.register(claim_main_bot_trial, F.data == "trial:claim")
        return router

    def reseller_keyboard_with_trial():
        markup = original_reseller_keyboard()
        rows = [list(row) for row in markup.keyboard]
        if not any(button.text == TRIAL_LABEL for row in rows for button in row):
            rows.append([KeyboardButton(text=TRIAL_LABEL)])
        return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=rows)

    def reseller_build_router_with_trial(reseller_id: int):
        router = original_reseller_build_router(reseller_id)

        async def claim_reseller_trial(message):
            db = reseller_bot_runtime.SessionLocal()
            try:
                user = reseller_bot_runtime.linked_user(
                    db,
                    int(reseller_id),
                    int(message.from_user.id),
                )
                if not user:
                    await message.answer("ابتدا /start را ارسال کنید")
                    return

                # Reseller Trial has its own setting + claim ledger. It never calls
                # the main Trial service and a main Trial claim cannot block it.
                from .services.reseller_trial_service import claim_reseller_trial_for_user

                result = await claim_reseller_trial_for_user(
                    db,
                    user_id=int(user.id),
                    reseller_id=int(reseller_id),
                )
                link = _delivery_link(result)
                lines = [
                    "🎁 <b>اکانت تست نماینده شما فعال شد</b>",
                    "",
                    f"📅 اعتبار: <b>{int(result.get('duration_days') or 1)} روز</b>",
                    f"📦 حجم: <b>{int(result.get('traffic_mb') or 500)} MB</b>",
                    f"🆔 اشتراک: <code>#{int(result.get('subscription_id') or 0)}</code>",
                ]
                if link:
                    lines.extend(["", "🔗 <b>لینک اتصال:</b>", f"<code>{escape(link)}</code>"])
                await message.answer("\n".join(lines), reply_markup=reseller_keyboard_with_trial())
            except Exception as exc:
                text, _ = _friendly_trial_error(exc)
                await message.answer(text, reply_markup=reseller_keyboard_with_trial())
            finally:
                db.close()

        router.message.register(claim_reseller_trial, F.text == TRIAL_LABEL)
        return router

    telegram_purchase_bot.create_purchase_router = create_purchase_router_with_trial
    reseller_bot_runtime._main_keyboard = reseller_keyboard_with_trial
    reseller_bot_runtime.build_router = reseller_build_router_with_trial
    _INSTALLED = True
