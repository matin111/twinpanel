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


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from . import reseller_bot_runtime, telegram_purchase_bot

    original_plans_keyboard = telegram_purchase_bot.plans_keyboard
    original_create_purchase_router = telegram_purchase_bot.create_purchase_router
    original_reseller_keyboard = reseller_bot_runtime._main_keyboard
    original_reseller_build_router = reseller_bot_runtime.build_router

    def plans_keyboard_with_trial(plans):
        markup = original_plans_keyboard(plans)
        rows = list(markup.inline_keyboard)
        if any(bool(plan.get("trial_enabled")) for plan in plans[:30]):
            rows.append([
                InlineKeyboardButton(
                    text=TRIAL_LABEL,
                    callback_data="trial:claim",
                )
            ])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def create_purchase_router_with_trial(request_fn, session_fn):
        router = original_create_purchase_router(request_fn, session_fn)

        async def claim_main_bot_trial(callback):
            try:
                parts = str(callback.data or "").split(":")
                payload: dict[str, Any] = {}
                # Keep old plan-specific callbacks functional for already-sent Telegram messages.
                if len(parts) > 2 and parts[2].isdigit():
                    payload["plan_id"] = int(parts[2])
                session = await session_fn(callback.from_user.id)
                token = session["access_token"]
                result = await request_fn(
                    "POST",
                    "/v1/trial/claim",
                    token=token,
                    payload=payload,
                )
            except Exception as exc:
                await callback.answer(str(exc), show_alert=True)
                return

            await callback.answer("اکانت تست ساخته شد")
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

        router.callback_query.register(
            claim_main_bot_trial,
            F.data.startswith("trial:claim"),
        )
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

                from .services.trial_service import claim_trial_for_user

                result = await claim_trial_for_user(
                    db,
                    user_id=int(user.id),
                    plan_id=None,
                    source="reseller_bot",
                    reseller_id=int(reseller_id),
                )
                link = _delivery_link(result)
                lines = [
                    "🎁 <b>اکانت تست شما فعال شد</b>",
                    "",
                    f"📅 اعتبار: <b>{int(result.get('duration_days') or 1)} روز</b>",
                    f"📦 حجم: <b>{int(result.get('traffic_mb') or 500)} MB</b>",
                    f"🆔 اشتراک: <code>#{int(result.get('subscription_id') or 0)}</code>",
                ]
                if link:
                    lines.extend(["", "🔗 <b>لینک اتصال:</b>", f"<code>{escape(link)}</code>"])
                await message.answer("\n".join(lines), reply_markup=reseller_keyboard_with_trial())
            except Exception as exc:
                detail = getattr(exc, "detail", str(exc))
                if isinstance(detail, dict):
                    detail = detail.get("message") or detail.get("code") or str(detail)
                await message.answer("❌ " + escape(str(detail)), reply_markup=reseller_keyboard_with_trial())
            finally:
                db.close()

        router.message.register(
            claim_reseller_trial,
            F.text == TRIAL_LABEL,
        )
        return router

    telegram_purchase_bot.plans_keyboard = plans_keyboard_with_trial
    telegram_purchase_bot.create_purchase_router = create_purchase_router_with_trial
    reseller_bot_runtime._main_keyboard = reseller_keyboard_with_trial
    reseller_bot_runtime.build_router = reseller_build_router_with_trial
    _INSTALLED = True
