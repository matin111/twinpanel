import asyncio
import os
import time
from datetime import datetime
from html import escape

import httpx

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from .routers.telegram_manager import load_bot_token
from .telegram_learning_center import register_learning_handlers


API_BASE = os.getenv(
    "TWINPANEL_API_BASE",
    "http://127.0.0.1:8095",
).rstrip("/")

def _load_internal_secret() -> str:
    value = os.getenv(
        "TWINPANEL_TELEGRAM_BOT_SECRET",
        "",
    ).strip()

    if value:
        return value

    # TWINPANEL_RUNTIME_SECRET_FALLBACK_V2
    try:
        with open(
            "/etc/twinpanel-telegram-api.env",
            "r",
            encoding="utf-8",
        ) as handle:
            for line in handle:
                if line.startswith(
                    "TWINPANEL_TELEGRAM_BOT_SECRET="
                ):
                    return (
                        line.split("=", 1)[1]
                        .strip()
                    )
    except Exception:
        pass

    return ""


BOT_SECRET = _load_internal_secret()


router = Router()

# TWINPANEL_MAIN_SHARED_LEARNING_V1
register_learning_handlers(router, prefix="mlearn")


class LinkState(StatesGroup):
    email = State()
    password = State()


class RenewalPaymentState(StatesGroup):
    proof = State()


def main_keyboard():
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [
                KeyboardButton(
                    text="🏠 داشبورد"
                ),
                KeyboardButton(
                    text="🛒 خرید اشتراک"
                ),
            ],
            [
                KeyboardButton(
                    text="📦 اشتراک‌های من"
                ),
                KeyboardButton(
                    text="💰 کیف پول"
                ),
            ],
            [
                KeyboardButton(
                    text="📚 آموزش"
                ),
                KeyboardButton(
                    text="⬇️ دانلود برنامه"
                ),
            ],
            [
                # TWINPANEL_MAIN_ACCOUNT_BUTTON_V1
                KeyboardButton(
                    text="🎫 پشتیبانی"
                ),
                KeyboardButton(
                    text="👤 حساب من"
                ),
            ],
        ],
    )


def connect_keyboard():
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [
                KeyboardButton(
                    text="🔗 اتصال حساب"
                )
            ]
        ],
    )


async def request(
    method,
    path,
    *,
    token=None,
    bot_auth=False,
    payload=None,
):
    headers = {}

    if token:
        headers["Authorization"] = (
            f"Bearer {token}"
        )

    if bot_auth:
        headers[
            "X-Telegram-Bot-Secret"
        ] = BOT_SECRET

    async with httpx.AsyncClient(
        timeout=20.0
    ) as client:
        response = await client.request(
            method,
            API_BASE + path,
            headers=headers,
            json=payload,
        )

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code >= 400:
        detail = (
            data.get("detail")
            if isinstance(data, dict)
            else None
        )

        raise RuntimeError(
            str(detail or "خطای پنل")
        )

    return data


async def status(tg_id):
    return await request(
        "GET",
        f"/v1/telegram/status/{tg_id}",
        bot_auth=True,
    )


async def session(
    tg_id,
    telegram_username=None,
    telegram_first_name=None,
):
    return await request(
        "POST",
        "/v1/telegram/ensure",
        bot_auth=True,
        payload={
            "telegram_id":
                int(tg_id),

            "telegram_username":
                telegram_username,

            "telegram_first_name":
                telegram_first_name,
        },
    )



# TWINPANEL_SUBSCRIPTION_BOT_V2

STATUS_FA = {
    "active": "فعال",
    "expired": "منقضی",
    "suspended": "متوقف",
    "canceled": "لغو شده",
    "pending": "در انتظار",
}


PROTOCOL_FA = {
    "cisco": "Cisco / OpenConnect",
    "openvpn": "OpenVPN",
    "wireguard": "WireGuard",
    "l2tp": "L2TP / IPsec",
    "v2ray": "V2Ray / Xray",
}


def _status_fa(value):
    value = str(value or "").lower()

    return STATUS_FA.get(
        value,
        value or "-"
    )


def _fmt_gb(value):
    try:
        value = float(value or 0)

        if value.is_integer():
            return str(int(value))

        return f"{value:.2f}"
    except Exception:
        return "0"


def _fmt_money(value):
    try:
        return f"{int(value or 0):,}"
    except Exception:
        return "0"


def _fmt_date(value):
    if not value:
        return "-"

    try:
        raw = str(value).replace(
            "Z",
            "+00:00",
        )

        dt = datetime.fromisoformat(raw)

        return dt.strftime("%Y/%m/%d")
    except Exception:
        return str(value)[:10]


def _protocols_text(rows):
    result = []

    for item in rows or []:
        result.append(
            PROTOCOL_FA.get(
                str(item).lower(),
                str(item),
            )
        )

    return " • ".join(result) or "-"


def _subscription_button_state(sub):
    status = str(
        sub.get("status")
        or ""
    ).strip().lower()

    try:
        days = int(
            sub.get("days_remaining")
            or 0
        )
    except Exception:
        days = 0

    try:
        total = float(
            sub.get("traffic_limit_gb")
            or 0
        )

        remaining = float(
            sub.get("traffic_remaining_gb")
            or 0
        )
    except Exception:
        total = 0
        remaining = 0

    # پایان کامل
    if (
        status in {
            "expired",
            "canceled",
            "cancelled",
        }
        or days <= 0
        or (
            total > 0
            and remaining <= 0
        )
    ):
        return "🔴", "اتمام"

    # نزدیک پایان:
    # 5 روز یا کمتر
    # یا 10 درصد حجم یا کمتر
    low_volume = (
        total > 0
        and (
            remaining / total
        ) <= 0.10
    )

    if (
        status == "active"
        and (
            days <= 5
            or low_volume
        )
    ):
        return "🟡", "در حال اتمام"

    if status == "active":
        return "🟢", "فعال"

    return "🟡", "متوقف"


def _subscription_button_username(sub):
    username = str(
        sub.get("account_username")
        or ""
    ).strip()

    if username:
        return username

    return (
        "#"
        + str(
            sub.get("id")
            or "-"
        )
    )


def subscription_list_keyboard(rows):
    buttons = []

    for sub in rows[:30]:
        sub_id = int(
            sub.get("id")
        )

        username = (
            _subscription_button_username(
                sub
            )
        )

        dot, state = (
            _subscription_button_state(
                sub
            )
        )

        plan = str(
            sub.get("plan_name")
            or "اشتراک"
        ).strip()

        # Telegram button:
        # 🟢 username | پلن
        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"{dot} 👤 {username}"
                )[:60],
                callback_data=(
                    f"sub:{sub_id}"
                ),
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )

def subscription_actions_keyboard(info):
    sub_id = int(info["id"])

    rows = []

    if info.get(
        "connection_available"
    ):
        rows.append([
            InlineKeyboardButton(
                text="🔗 اطلاعات اتصال",
                callback_data=(
                    f"subconn:{sub_id}"
                ),
            )
        ])

    if info.get("can_renew"):
        rows.append([
            InlineKeyboardButton(
                text="🔄 تمدید اکانت",
                callback_data=(
                    f"subrenew:{sub_id}"
                ),
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="♻️ بروزرسانی",
            callback_data=(
                f"sub:{sub_id}"
            ),
        ),
        InlineKeyboardButton(
            text="⬅️ اشتراک‌های من",
            callback_data="subs:list",
        ),
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def renewal_confirm_keyboard(sub_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ ادامه و پرداخت",
                    callback_data=(
                        f"renewconfirm:{sub_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ بازگشت",
                    callback_data=f"sub:{sub_id}",
                )
            ],
        ]
    )


def renewal_payment_methods_keyboard(
    order_id,
    methods,
):
    rows = []

    for method in methods:
        method_id = str(
            method.get("id") or ""
        )

        if not method_id:
            continue

        title = str(
            method.get("title")
            or method_id
        )

        rows.append([
            InlineKeyboardButton(
                text=f"💳 {title}",
                callback_data=(
                    f"renewpay:"
                    f"{order_id}:"
                    f"{method_id}"
                ),
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def renewal_proof_keyboard(
    intent_id,
    method,
):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ ثبت اطلاعات پرداخت",
                    callback_data=(
                        f"renewproof:"
                        f"{intent_id}:"
                        f"{method}"
                    ),
                )
            ]
        ]
    )


async def _telegram_session_token(
    telegram_id,
):
    auth = await session(
        telegram_id
    )

    return auth["access_token"]


async def _load_subscription_manage(
    telegram_id,
    subscription_id,
):
    token = await _telegram_session_token(
        telegram_id
    )

    info = await request(
        "GET",
        (
            "/v1/customer/subscriptions/"
            f"{subscription_id}/manage"
        ),
        token=token,
    )

    return token, info


# TWINPANEL_LIST_REAL_USERNAME_V2
async def _enrich_subscription_rows(
    telegram_id,
    rows,
    token=None,
):
    """
    /subscriptions/me is intentionally lightweight.
    For Telegram account list we also need the real
    VPN account username.

    The manage endpoint contains the canonical
    account_username and legacy credential fallback.
    """

    if not rows:
        return []

    if token is None:
        token = await _telegram_session_token(
            telegram_id
        )

    async def load_one(row):
        item = dict(row)

        try:
            sub_id = int(
                item.get("id")
            )

            manage = await request(
                "GET",
                (
                    "/v1/customer/subscriptions/"
                    f"{sub_id}/manage"
                ),
                token=token,
            )

            username = str(
                manage.get(
                    "account_username"
                )
                or ""
            ).strip()

            if username:
                item[
                    "account_username"
                ] = username

            # Use manage values as canonical state too.
            for key in (
                "status",
                "days_remaining",
                "traffic_limit_gb",
                "traffic_used_gb",
                "traffic_remaining_gb",
                "plan_name",
                "expires_at",
            ):
                if (
                    key in manage
                    and manage.get(key)
                    is not None
                ):
                    item[key] = manage[key]

        except Exception:
            # One old/broken subscription must not
            # prevent the whole list from opening.
            pass

        return item

    return list(
        await asyncio.gather(
            *[
                load_one(row)
                for row in rows
            ]
        )
    )


def _subscription_text(info):
    limit = float(
        info.get(
            "traffic_limit_gb",
            0,
        ) or 0
    )

    used = float(
        info.get(
            "traffic_used_gb",
            0,
        ) or 0
    )

    remaining = float(
        info.get(
            "traffic_remaining_gb",
            0,
        ) or 0
    )

    percent = 0

    if limit > 0:
        percent = min(
            100,
            max(
                0,
                round(
                    used * 100 / limit
                ),
            ),
        )

    plan = (
        escape(
            str(
                info.get("plan_name")
                or "اشتراک"
            )
        )
    )

    # TWINPANEL_BOT_USERNAME_DISPLAY_V1
    account_username = escape(
        str(
            info.get("account_username")
            or "ثبت نشده"
        )
    )

    return (
        f"📦 <b>{plan}</b>\n\n"

        f"👤 نام کاربری: "
        f"<code>{account_username}</code>\n"

        f"🆔 شناسه اشتراک: "
        f"<code>#{info.get('id')}</code>\n\n"

        f"🟢 وضعیت: "
        f"<b>{escape(_status_fa(info.get('status')))}</b>\n"

        f"📅 شروع: "
        f"<b>{escape(_fmt_date(info.get('starts_at')))}</b>\n"

        f"⏰ انقضا: "
        f"<b>{escape(_fmt_date(info.get('expires_at')))}</b>\n"

        f"⌛ روز باقی‌مانده: "
        f"<b>{int(info.get('days_remaining') or 0)}</b>\n\n"

        f"📊 حجم کل: "
        f"<b>{_fmt_gb(limit)} GB</b>\n"

        f"📉 مصرف‌شده: "
        f"<b>{_fmt_gb(used)} GB</b>\n"

        f"📈 باقی‌مانده: "
        f"<b>{_fmt_gb(remaining)} GB</b>\n"

        f"📌 مصرف: "
        f"<b>{percent}%</b>\n\n"

        f"📱 تعداد دستگاه: "
        f"<b>{int(info.get('device_limit') or 0)}</b>\n\n"

        f"🌐 پروتکل‌ها:\n"
        f"<b>{escape(_protocols_text(info.get('protocols')))}</b>"
    )



@router.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
):
    await state.clear()

    try:
        # کاربر جدید به‌صورت خودکار ساخته می‌شود
        # و کاربر قبلی همان حساب قبلی را دریافت می‌کند.
        await session(
            message.from_user.id,
            telegram_username=(
                message.from_user.username
            ),
            telegram_first_name=(
                message.from_user.first_name
            ),
        )

    except Exception as exc:
        await message.answer(
            "❌ ارتباط با Twin Panel برقرار نشد.\n\n"
            + escape(str(exc))
        )
        return

    first_name = str(
        message.from_user.first_name
        or ""
    ).strip()

    greeting = (
        f"👋 <b>{escape(first_name)} عزیز، "
        "به Twin Panel خوش آمدید</b>"
        if first_name
        else
        "👋 <b>به Twin Panel خوش آمدید</b>"
    )

    text = (
        f"{greeting}\n\n"

        "مدیریت و خرید اشتراک VPN "
        "از داخل تلگرام.\n\n"

        "از طریق ربات می‌توانید:\n\n"

        "🛒 اشتراک جدید تهیه کنید\n"
        "📦 اکانت‌های خود را مدیریت کنید\n"
        "🔗 اطلاعات اتصال را دریافت کنید\n"
        "🔄 اشتراک خود را تمدید کنید\n"
        "💰 کیف پول خود را مدیریت کنید\n"
        "📚 آموزش اتصال را مشاهده کنید\n"
        "⬇️ برنامه مناسب دستگاه خود را دانلود کنید\n"
        "🎫 با پشتیبانی در ارتباط باشید\n\n"

        "از منوی زیر بخش موردنظر را انتخاب کنید."
    )

    await message.answer(
        text,
        reply_markup=main_keyboard(),
    )


@router.message(
    F.text == "🔗 اتصال حساب"
)
async def begin_link(
    message: Message,
    state: FSMContext,
):
    await state.set_state(
        LinkState.email
    )

    await message.answer(
        "ایمیل حساب Twin Panel را وارد کنید."
    )


@router.message(LinkState.email)
async def link_email(
    message: Message,
    state: FSMContext,
):
    email = (
        message.text
        or ""
    ).strip().lower()

    if "@" not in email:
        await message.answer(
            "ایمیل معتبر وارد کنید."
        )
        return

    await state.update_data(
        email=email
    )

    await state.set_state(
        LinkState.password
    )

    await message.answer(
        "رمز عبور حساب را وارد کنید."
    )


@router.message(LinkState.password)
async def link_password(
    message: Message,
    state: FSMContext,
):
    data = await state.get_data()
    password = message.text or ""

    try:
        try:
            await message.delete()
        except Exception:
            pass

        result = await request(
            "POST",
            "/v1/telegram/link",
            bot_auth=True,
            payload={
                "telegram_id":
                    message.from_user.id,
                "telegram_username":
                    message.from_user.username,
                "telegram_first_name":
                    message.from_user.first_name,
                "email":
                    data["email"],
                "password":
                    password,
            },
        )

    except Exception as exc:
        await state.clear()

        await message.answer(
            "❌ "
            + escape(str(exc)),
            reply_markup=connect_keyboard(),
        )
        return

    finally:
        password = ""

    await state.clear()

    user = result.get("user") or {}

    await message.answer(
        "✅ حساب متصل شد.\n\n"
        f"{escape(str(user.get('email') or ''))}",
        reply_markup=main_keyboard(),
    )



# TWINPANEL_CUSTOMER_DASHBOARD_V2
async def _customer_dashboard_data(
    telegram_id: int,
):
    token = await _telegram_session_token(
        telegram_id
    )

    me, subscriptions, orders, payments = (
        await asyncio.gather(
            request(
                "GET",
                "/v1/auth/me",
                token=token,
            ),
            request(
                "GET",
                "/v1/subscriptions/me",
                token=token,
            ),
            request(
                "GET",
                "/v1/store/orders/me",
                token=token,
            ),
            request(
                "GET",
                "/v1/payments/intents/me",
                token=token,
            ),
        )
    )

    subscriptions = (
        subscriptions
        if isinstance(subscriptions, list)
        else []
    )

    orders = (
        orders
        if isinstance(orders, list)
        else []
    )

    payments = (
        payments
        if isinstance(payments, list)
        else []
    )

    active = []
    suspended = []
    ended = []
    expiring = []

    for item in subscriptions:
        status = str(
            item.get("status")
            or ""
        ).lower()

        try:
            days = int(
                item.get("days_remaining")
                or 0
            )
        except Exception:
            days = 0

        try:
            total = float(
                item.get("traffic_limit_gb")
                or 0
            )

            remaining = float(
                item.get("traffic_remaining_gb")
                or 0
            )
        except Exception:
            total = 0
            remaining = 0

        if status == "active":
            active.append(item)

            low_volume = (
                total > 0
                and (
                    remaining / total
                ) <= 0.10
            )

            if (
                days <= 5
                or low_volume
            ):
                expiring.append(item)

        elif status == "suspended":
            suspended.append(item)

        elif status in {
            "expired",
            "canceled",
            "cancelled",
        }:
            ended.append(item)

    current = (
        active[0]
        if active
        else (
            subscriptions[0]
            if subscriptions
            else None
        )
    )

    current_info = None

    if current:
        try:
            current_info = await request(
                "GET",
                (
                    "/v1/customer/subscriptions/"
                    f"{int(current['id'])}/manage"
                ),
                token=token,
            )
        except Exception:
            current_info = dict(current)

    pending_payment_statuses = {
        "pending_payment",
        "payment_submitted",
        "awaiting_review",
    }

    pending_payments = sum(
        1
        for item in payments
        if str(
            item.get("status")
            or ""
        ).lower()
        in pending_payment_statuses
    )

    return {
        "me": me or {},
        "subscriptions": subscriptions,
        "active": active,
        "expiring": expiring,
        "suspended": suspended,
        "ended": ended,
        "current": current_info,
        "orders": orders,
        "payments": payments,
        "pending_payments": pending_payments,
    }


def _dashboard_status_fa(
    value,
    kind="order",
):
    value = str(
        value or ""
    ).lower()

    if kind == "payment":
        mapping = {
            "pending_payment":
                "در انتظار پرداخت",
            "payment_submitted":
                "ثبت اطلاعات",
            "awaiting_review":
                "در انتظار بررسی",
            "approved":
                "تأیید شده",
            "auto_verified":
                "تأیید خودکار",
            "rejected":
                "رد شده",
        }

    else:
        mapping = {
            "pending_payment":
                "در انتظار پرداخت",
            "awaiting_review":
                "در انتظار بررسی",
            "paid":
                "پرداخت شده",
            "provisioning":
                "در حال ساخت اکانت",
            "fulfilled":
                "تکمیل شده",
            "provision_failed":
                "خطای ساخت",
            "canceled":
                "لغو شده",
        }

    return mapping.get(
        value,
        value or "-"
    )


def _dashboard_text(data):
    me = data["me"]

    email = str(
        me.get("email")
        or "-"
    )

    name = str(
        me.get("full_name")
        or ""
    ).strip()

    if not name:
        name = (
            email.split("@")[0]
            if "@" in email
            else "کاربر"
        )

    current = data.get("current")

    lines = [
        "🏠 <b>داشبورد</b>",
        "",
        f"👤 <b>{escape(name)}</b>",
        f"📧 <code>{escape(email)}</code>",
        "",
        "📦 <b>وضعیت اشتراک‌ها</b>",
        f"🟢 فعال: <b>{len(data['active'])}</b>",
        (
            "🟡 نزدیک اتمام: "
            f"<b>{len(data['expiring'])}</b>"
        ),
        (
            "⏸ معلق: "
            f"<b>{len(data['suspended'])}</b>"
        ),
        (
            "🔴 پایان‌یافته: "
            f"<b>{len(data['ended'])}</b>"
        ),
    ]

    if current:
        username = str(
            current.get(
                "account_username"
            )
            or "-"
        ).strip()

        remaining = current.get(
            "traffic_remaining_gb"
        )

        used = current.get(
            "traffic_used_gb"
        )

        total = current.get(
            "traffic_limit_gb"
        )

        days = int(
            current.get(
                "days_remaining"
            )
            or 0
        )

        device_limit = int(
            current.get(
                "device_limit"
            )
            or 0
        )

        protocols = (
            current.get("protocols")
            or []
        )

        lines.extend([
            "",
            "⭐ <b>اشتراک فعلی</b>",
            (
                "👤 نام کاربری: "
                f"<code>{escape(username)}</code>"
            ),
            (
                "📈 حجم باقی‌مانده: "
                f"<b>{_fmt_gb(remaining)} GB</b>"
            ),
            (
                "📉 مصرف‌شده: "
                f"<b>{_fmt_gb(used)} GB</b>"
            ),
            (
                "📊 حجم کل: "
                f"<b>{_fmt_gb(total)} GB</b>"
            ),
            (
                "⌛ اعتبار باقی‌مانده: "
                f"<b>{days} روز</b>"
            ),
            (
                "📅 انقضا: "
                f"<b>{escape(_fmt_date(current.get('expires_at')))}</b>"
            ),
            (
                "📱 دستگاه: "
                f"<b>{device_limit}</b>"
            ),
            (
                "🌐 پروتکل فعال: "
                f"<b>{len(protocols)}</b>"
            ),
        ])

    payments = data["payments"]

    if payments:
        last_payment = payments[0]

        amount = int(
            last_payment.get(
                "payable_amount_toman"
            )
            or last_payment.get(
                "base_amount_toman"
            )
            or 0
        )

        payment_status = (
            _dashboard_status_fa(
                last_payment.get("status"),
                "payment",
            )
        )

        lines.extend([
            "",
            "💳 <b>آخرین پرداخت</b>",
            (
                f"{escape(payment_status)}"
                f" • <b>{amount:,} تومان</b>"
            ),
        ])

        if data["pending_payments"]:
            lines.append(
                "🟡 در انتظار بررسی: "
                f"<b>{data['pending_payments']}</b>"
            )

    orders = data["orders"]

    if orders:
        last_order = orders[0]

        order_status = (
            _dashboard_status_fa(
                last_order.get("status"),
                "order",
            )
        )

        lines.extend([
            "",
            "🧾 <b>آخرین سفارش</b>",
            (
                f"#{last_order.get('id')} "
                f"• {escape(order_status)}"
            ),
        ])

    return "\n".join(lines)


def _dashboard_keyboard(data):
    rows = []

    current = data.get("current")

    if current and current.get("id"):
        username = str(
            current.get(
                "account_username"
            )
            or "اشتراک فعلی"
        )

        rows.append([
            InlineKeyboardButton(
                text=(
                    f"👤 مدیریت {username}"
                )[:60],
                callback_data=(
                    f"sub:{int(current['id'])}"
                ),
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="📦 همه اشتراک‌ها",
            callback_data="subs:list",
        ),
        InlineKeyboardButton(
            text="🛒 خرید اشتراک",
            callback_data="shop:list",
        ),
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


@router.message(
    F.text == "🏠 داشبورد"
)
async def customer_dashboard(
    message: Message,
):
    try:
        data = (
            await _customer_dashboard_data(
                message.from_user.id
            )
        )

    except Exception as exc:
        await message.answer(
            "❌ دریافت داشبورد ناموفق بود:\n"
            + escape(str(exc))
        )
        return

    await message.answer(
        _dashboard_text(data),
        reply_markup=(
            _dashboard_keyboard(data)
        ),
    )



@router.message(
    F.text == "📦 اشتراک‌های من"
)
async def subscriptions(
    message: Message,
):
    try:
        token = (
            await _telegram_session_token(
                message.from_user.id
            )
        )

        rows = await request(
            "GET",
            "/v1/subscriptions/me",
            token=token,
        )

        # TWINPANEL_ENRICH_LIST_CALL_V2
        rows = await _enrich_subscription_rows(
            message.from_user.id,
            rows,
            token=token,
        )

    except Exception as exc:
        await message.answer(
            "❌ "
            + escape(str(exc))
        )
        return

    if not rows:
        await message.answer(
            "📦 هنوز اشتراکی ندارید."
        )
        return

    active = sum(
        1
        for row in rows
        if str(
            row.get("status") or ""
        ).lower() == "active"
    )

    await message.answer(
        "<b>📦 اشتراک‌های من</b>\n\n"
        f"تعداد اشتراک‌ها: <b>{len(rows)}</b>\n"
        f"اشتراک فعال: <b>{active}</b>\n\n"
        "برای مدیریت، یک اشتراک را انتخاب کنید.\n\n"
        "🟢 فعال   🟡 در حال اتمام   🔴 اتمام",
        reply_markup=(
            subscription_list_keyboard(
                rows
            )
        ),
    )


@router.callback_query(
    F.data == "subs:list"
)
async def subscriptions_callback(
    callback: CallbackQuery,
):
    try:
        token = (
            await _telegram_session_token(
                callback.from_user.id
            )
        )

        rows = await request(
            "GET",
            "/v1/subscriptions/me",
            token=token,
        )

        rows = await _enrich_subscription_rows(
            callback.from_user.id,
            rows,
            token=token,
        )

    except Exception as exc:
        await callback.answer(
            str(exc),
            show_alert=True,
        )
        return

    await callback.answer()

    if not rows:
        await callback.message.edit_text(
            "📦 هنوز اشتراکی ندارید."
        )
        return

    active = sum(
        1
        for row in rows
        if str(
            row.get("status") or ""
        ).lower() == "active"
    )

    await callback.message.edit_text(
        "<b>📦 اشتراک‌های من</b>\n\n"
        f"تعداد اشتراک‌ها: <b>{len(rows)}</b>\n"
        f"اشتراک فعال: <b>{active}</b>\n\n"
        "یک اشتراک را انتخاب کنید.\n\n"
        "🟢 فعال   🟡 در حال اتمام   🔴 اتمام",
        reply_markup=(
            subscription_list_keyboard(
                rows
            )
        ),
    )


@router.callback_query(
    F.data.startswith("sub:")
)
async def subscription_detail(
    callback: CallbackQuery,
):
    try:
        sub_id = int(
            callback.data.split(":")[1]
        )

        _, info = (
            await _load_subscription_manage(
                callback.from_user.id,
                sub_id,
            )
        )

    except Exception as exc:
        await callback.answer(
            str(exc),
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        _subscription_text(info),
        reply_markup=(
            subscription_actions_keyboard(
                info
            )
        ),
    )


@router.callback_query(
    F.data.startswith("subconn:")
)
async def subscription_connection(
    callback: CallbackQuery,
):
    try:
        sub_id = int(
            callback.data.split(":")[1]
        )

        token = (
            await _telegram_session_token(
                callback.from_user.id
            )
        )

        info = await request(
            "GET",
            (
                "/v1/customer/subscriptions/"
                f"{sub_id}/connection-info"
            ),
            token=token,
        )

        link = (
            info.get("subscription_link")
            or ""
        ).strip()

        if not link:
            raise RuntimeError(
                "لینک اتصال هنوز آماده نیست"
            )

    except Exception as exc:
        await callback.answer(
            str(exc),
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.answer(
        f"🔗 <b>اطلاعات اتصال اشتراک #{sub_id}</b>\n\n"
        "لینک زیر شامل اطلاعات اتصال و "
        "کانفیگ‌های اشتراک شماست:\n\n"
        f"<code>{escape(link)}</code>\n\n"
        "این لینک را فقط برای دستگاه‌های "
        "خودتان استفاده کنید."
    )


@router.callback_query(
    F.data.startswith("subrenew:")
)
async def subscription_renew(
    callback: CallbackQuery,
):
    try:
        sub_id = int(
            callback.data.split(":")[1]
        )

        _, info = (
            await _load_subscription_manage(
                callback.from_user.id,
                sub_id,
            )
        )

        plan = (
            info.get("renew_plan")
            or {}
        )

        if not plan:
            raise RuntimeError(
                "پلن این اشتراک برای تمدید فعال نیست"
            )

    except Exception as exc:
        await callback.answer(
            str(exc),
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        f"🔄 <b>تمدید اشتراک #{sub_id}</b>\n\n"
        f"پلن: <b>{escape(str(plan.get('name') or '-'))}</b>\n"
        f"➕ حجم: <b>{int(plan.get('traffic_gb') or 0)} GB</b>\n"
        f"➕ اعتبار: <b>{int(plan.get('duration_days') or 0)} روز</b>\n"
        f"💳 مبلغ: <b>{_fmt_money(plan.get('price_toman'))} تومان</b>\n\n"
        "بعد از تأیید پرداخت، همین اکانت تمدید "
        "می‌شود و اکانت جدید ساخته نمی‌شود.",
        reply_markup=(
            renewal_confirm_keyboard(
                sub_id
            )
        ),
    )


@router.callback_query(
    F.data.startswith("renewconfirm:")
)
async def renewal_create_order(
    callback: CallbackQuery,
):
    try:
        sub_id = int(
            callback.data.split(":")[1]
        )

        token = (
            await _telegram_session_token(
                callback.from_user.id
            )
        )

        order = await request(
            "POST",
            (
                "/v1/customer/subscriptions/"
                f"{sub_id}/renew-order"
            ),
            token=token,
            payload={
                "idempotency_key": (
                    "tg-renew-"
                    f"{callback.from_user.id}-"
                    f"{sub_id}-"
                    f"{int(time.time())}"
                )
            },
        )

        method_data = await request(
            "GET",
            "/v1/payments/methods",
        )

        methods = (
            method_data.get("methods")
            or []
        )

        if not methods:
            raise RuntimeError(
                "روش پرداخت فعالی وجود ندارد"
            )

    except Exception as exc:
        await callback.answer(
            str(exc),
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.edit_text(
        "✅ <b>سفارش تمدید ساخته شد</b>\n\n"
        f"شماره سفارش: "
        f"<b>#{order.get('id')}</b>\n"
        f"مبلغ: "
        f"<b>{_fmt_money(order.get('amount_toman'))} تومان</b>\n\n"
        "روش پرداخت را انتخاب کنید:",
        reply_markup=(
            renewal_payment_methods_keyboard(
                int(order["id"]),
                methods,
            )
        ),
    )


@router.callback_query(
    F.data.startswith("renewpay:")
)
async def renewal_payment_method(
    callback: CallbackQuery,
):
    try:
        parts = callback.data.split(
            ":",
            2,
        )

        order_id = int(parts[1])
        method_id = parts[2]

        token = (
            await _telegram_session_token(
                callback.from_user.id
            )
        )

        intent = await request(
            "POST",
            "/v1/payments/intents",
            token=token,
            payload={
                "order_id": order_id,
                "method": method_id,
            },
        )

        method_data = await request(
            "GET",
            "/v1/payments/methods",
        )

        methods = (
            method_data.get("methods")
            or []
        )

        method = next(
            (
                row
                for row in methods
                if row.get("id")
                == method_id
            ),
            {},
        )

    except Exception as exc:
        await callback.answer(
            str(exc),
            show_alert=True,
        )
        return

    await callback.answer()

    title = escape(
        str(
            method.get("title")
            or method_id
        )
    )

    text = (
        f"💳 <b>{title}</b>\n\n"
        f"مبلغ قابل پرداخت: "
        f"<b>{_fmt_money(intent.get('payable_amount_toman'))} تومان</b>\n"
    )

    if method_id == "card_to_card":

        text += (
            "\nشماره کارت:\n"
            f"<code>{escape(str(method.get('card_number') or '-'))}</code>\n"
            f"به نام: "
            f"<b>{escape(str(method.get('card_holder') or '-'))}</b>\n"
        )

    else:

        text += (
            "\nآدرس کیف پول:\n"
            f"<code>{escape(str(method.get('address') or '-'))}</code>\n"
        )

        if intent.get(
            "crypto_amount_usdt"
        ):
            text += (
                "مقدار USDT: "
                f"<b>{escape(str(intent.get('crypto_amount_usdt')))}</b>\n"
            )

    text += (
        "\nپس از انتقال وجه، دکمه زیر را بزنید."
    )

    await callback.message.edit_text(
        text,
        reply_markup=(
            renewal_proof_keyboard(
                int(intent["id"]),
                method_id,
            )
        ),
    )


@router.callback_query(
    F.data.startswith("renewproof:")
)
async def renewal_proof_start(
    callback: CallbackQuery,
    state: FSMContext,
):
    try:
        parts = callback.data.split(
            ":",
            2,
        )

        intent_id = int(parts[1])
        method = parts[2]

    except Exception:
        await callback.answer(
            "اطلاعات پرداخت نامعتبر است",
            show_alert=True,
        )
        return

    await state.clear()

    await state.update_data(
        intent_id=intent_id,
        payment_method=method,
    )

    await state.set_state(
        RenewalPaymentState.proof
    )

    await callback.answer()

    if method == "card_to_card":
        await callback.message.answer(
            "کد پیگیری تراکنش کارت‌به‌کارت "
            "را ارسال کنید."
        )
    else:
        await callback.message.answer(
            "TXID تراکنش USDT را ارسال کنید."
        )


@router.message(
    RenewalPaymentState.proof
)
async def renewal_proof_submit(
    message: Message,
    state: FSMContext,
):
    value = (
        message.text
        or ""
    ).strip()

    if len(value) < 3:
        await message.answer(
            "❌ اطلاعات تراکنش معتبر نیست."
        )
        return

    data = await state.get_data()

    try:
        token = (
            await _telegram_session_token(
                message.from_user.id
            )
        )

        payload = {}

        if (
            data.get("payment_method")
            == "card_to_card"
        ):
            payload[
                "tracking_code"
            ] = value
        else:
            payload["txid"] = value

        result = await request(
            "POST",
            (
                "/v1/payments/intents/"
                f"{data['intent_id']}/submit"
            ),
            token=token,
            payload=payload,
        )

    except Exception as exc:
        await state.clear()

        await message.answer(
            "❌ "
            + escape(str(exc))
        )
        return

    await state.clear()

    await message.answer(
        "✅ <b>اطلاعات پرداخت ثبت شد</b>\n\n"
        "پس از تأیید پرداخت، همان اشتراک "
        "به‌صورت خودکار تمدید می‌شود.\n\n"
        f"وضعیت پرداخت: "
        f"<b>{escape(str(result.get('status') or 'ثبت شده'))}</b>",
        reply_markup=main_keyboard(),
    )




@router.message(
    F.text == "👤 حساب من"
)
async def account(
    message: Message,
):
    try:
        result = await status(
            message.from_user.id
        )

        user = result.get("user") or {}

    except Exception as exc:
        await message.answer(
            "❌ " + escape(str(exc))
        )
        return

    await message.answer(
        "<b>حساب من</b>\n\n"
        f"نام: {escape(str(user.get('full_name') or '-'))}\n"
        f"ایمیل: {escape(str(user.get('email') or '-'))}"
    )



# TWINPANEL_BACKUP_CHAT_ID_COMMAND_V1
@router.message(Command("backupid"))
async def backup_chat_id(
    message,
):

    chat = message.chat

    raw_type = getattr(
        chat,
        "type",
        "",
    )

    chat_type = str(
        getattr(
            raw_type,
            "value",
            raw_type,
        )
        or ""
    )

    if chat_type not in {
        "group",
        "supergroup",
        "channel",
    }:
        await message.answer(
            "این دستور را داخل گروه "
            "بکاپ ارسال کنید."
        )
        return

    type_fa = {
        "group": "گروه",
        "supergroup": "سوپرگروه",
        "channel": "کانال",
    }.get(
        chat_type,
        chat_type,
    )

    title = (
        getattr(
            chat,
            "title",
            None,
        )
        or "-"
    )

    await message.answer(
        "شناسه تلگرام بکاپ\n\n"
        f"عنوان: {title}\n"
        f"نوع: {type_fa}\n"
        f"Chat ID: {chat.id}\n\n"
        "این Chat ID را در "
        "TwinPanel > بکاپ وارد کنید."
    )


@router.message()
async def other(
    message: Message,
):
    await message.answer(
        "این بخش در حال اتصال به "
        "Twin Panel است."
    )



# TWINPANEL_NOTIFICATION_WORKER_V1
async def _telegram_notification_worker(bot):
    from datetime import datetime

    from sqlalchemy import (
        inspect as sa_inspect,
        text as sa_text,
    )

    from .database import SessionLocal
    from .telegram_notify_models import (
        TelegramNotification,
    )

    def linked_telegram_id(
        db,
        user_id,
    ):
        inspector = sa_inspect(
            db.get_bind()
        )

        names = {
            c["name"]
            for c in inspector.get_columns(
                "telegram_user_links"
            )
        }

        if "telegram_user_id" in names:
            tg_col = "telegram_user_id"
        elif "telegram_id" in names:
            tg_col = "telegram_id"
        else:
            return None

        order_col = (
            "id"
            if "id" in names
            else tg_col
        )

        active_sql = (
            " AND is_active = true"
            if "is_active" in names
            else ""
        )

        query = sa_text(
            f"""
            SELECT {tg_col}
            FROM telegram_user_links
            WHERE user_id = :user_id
            {active_sql}
            ORDER BY {order_col} DESC
            LIMIT 1
            """
        )

        value = db.execute(
            query,
            {"user_id": int(user_id)},
        ).scalar()

        return (
            int(value)
            if value is not None
            else None
        )

    while True:
        db = SessionLocal()

        try:
            rows = (
                db.query(
                    TelegramNotification
                )
                .filter(
                    TelegramNotification
                    .delivered_at
                    .is_(None)
                )
                .order_by(
                    TelegramNotification.id.asc()
                )
                .limit(20)
                .all()
            )

            for row in rows:
                telegram_id = (
                    linked_telegram_id(
                        db,
                        row.user_id,
                    )
                )

                if not telegram_id:
                    row.attempts += 1
                    row.last_error = (
                        "telegram link not found"
                    )
                    db.commit()
                    continue

                payload = row.payload or {}

                if (
                    row.kind
                    == "payment_approved"
                ):
                    username = str(
                        payload.get("username")
                        or ""
                    ).strip()

                    sub_id = (
                        payload.get(
                            "subscription_id"
                        )
                    )

                    # TWINPANEL_NOTIFY_USERNAME_FALLBACK_V1
                    if (
                        not username
                        or username == "-"
                    ) and sub_id:
                        try:
                            from .models import (
                                ProtocolCredential,
                                Subscription,
                            )

                            sub = db.get(
                                Subscription,
                                int(sub_id),
                            )

                            if (
                                sub
                                and sub.account_username
                            ):
                                username = str(
                                    sub.account_username
                                ).strip()

                            if not username:
                                credential = (
                                    db.query(
                                        ProtocolCredential
                                    )
                                    .filter(
                                        ProtocolCredential.subscription_id
                                        == int(sub_id),
                                        ProtocolCredential.username
                                        .isnot(None),
                                        ProtocolCredential.username
                                        != "",
                                    )
                                    .order_by(
                                        ProtocolCredential.id.asc()
                                    )
                                    .first()
                                )

                                if credential:
                                    username = str(
                                        credential.username
                                    ).strip()

                        except Exception:
                            pass

                    # TWINPANEL_MAIN_PAYMENT_DELIVERY_V2
                    password = ""
                    subscription_link = ""

                    if sub_id:
                        try:
                            from .models import (
                                Subscription,
                            )

                            from .routers.account_delivery import (
                                _stored_info,
                            )

                            delivery_sub = db.get(
                                Subscription,
                                int(sub_id),
                            )

                            if delivery_sub:
                                delivery_info = (
                                    _stored_info(
                                        db,
                                        delivery_sub,
                                    )
                                    or {}
                                )

                                account = (
                                    delivery_info.get(
                                        "account"
                                    )
                                    or {}
                                )

                                if (
                                    not username
                                    or username == "-"
                                ):
                                    username = str(
                                        account.get(
                                            "username"
                                        )
                                        or ""
                                    ).strip()

                                password = str(
                                    account.get(
                                        "password"
                                    )
                                    or ""
                                ).strip()

                                subscription_link = str(
                                    delivery_info.get(
                                        "subscription_link"
                                    )
                                    or ""
                                ).strip()

                        except Exception:
                            pass

                    if not username:
                        username = "-"

                    amount = int(
                        payload.get(
                            "amount_toman"
                        )
                        or 0
                    )

                    safe_username = escape(
                        username
                    )

                    safe_password = escape(
                        password
                    )

                    safe_link = escape(
                        subscription_link
                    )

                    order_id = escape(
                        str(
                            payload.get(
                                "order_id"
                            )
                            or "-"
                        )
                    )

                    lines = [
                        "✅ <b>پرداخت شما تأیید شد</b>",
                        "",
                        (
                            "🧾 سفارش: "
                            f"<b>#{order_id}</b>"
                        ),
                        (
                            "💰 مبلغ: "
                            f"<b>{amount:,} تومان</b>"
                        ),
                        "",
                        "🎉 <b>اشتراک شما فعال شد</b>",
                        (
                            "👤 نام کاربری: "
                            f"<code>{safe_username}</code>"
                        ),
                    ]

                    if password:
                        lines.append(
                            (
                                "🔑 رمز عبور: "
                                f"<code>{safe_password}</code>"
                            )
                        )

                    if sub_id:
                        lines.append(
                            (
                                "🆔 اشتراک: "
                                f"<code>#{int(sub_id)}</code>"
                            )
                        )

                    if subscription_link:
                        lines.extend([
                            "",
                            "🔗 <b>لینک اتصال:</b>",
                            f"<code>{safe_link}</code>",
                        ])

                    lines.extend([
                        "",
                        (
                            "اطلاعات سرویس از بخش "
                            "«اشتراک‌های من» نیز "
                            "در دسترس است."
                        ),
                    ])

                    text = "\n".join(
                        lines
                    )

                    buttons = []

                    if (
                        subscription_link.startswith(
                            "https://"
                        )
                        or subscription_link.startswith(
                            "http://"
                        )
                    ):
                        buttons.append([
                            InlineKeyboardButton(
                                text=(
                                    "🔗 باز کردن لینک اتصال"
                                ),
                                url=subscription_link,
                            )
                        ])

                    buttons.append([
                        InlineKeyboardButton(
                            text="📦 اشتراک‌های من",
                            callback_data="subs:list",
                        )
                    ])

                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=buttons
                    )

                elif (
                    row.kind
                    == "payment_rejected"
                ):
                    reason = str(
                        payload.get("reason")
                        or "دلیل ثبت نشده"
                    )

                    text = (
                        "❌ <b>پرداخت تأیید نشد</b>\n\n"

                        f"🧾 سفارش: "
                        f"<b>#{payload.get('order_id')}</b>\n\n"

                        f"دلیل:\n"
                        f"{reason}\n\n"

                        "می‌توانید اطلاعات پرداخت "
                        "را بررسی و دوباره اقدام کنید."
                    )

                    keyboard = None

                # TWINPANEL_SUPPORT_REPLY_WORKER_V1
                elif (
                    row.kind
                    == "support_reply"
                ):
                    ticket_id = int(
                        payload.get("ticket_id")
                        or 0
                    )

                    reply_text = str(
                        payload.get("message")
                        or ""
                    ).strip()

                    attachment_ref = str(
                        payload.get(
                            "attachment_ref"
                        )
                        or ""
                    ).strip()

                    text = (
                        "💬 <b>پاسخ پشتیبانی</b>"
                    )

                    if reply_text:
                        text += (
                            "\n\n"
                            + escape(reply_text)
                        )

                    if attachment_ref:
                        text += (
                            "\n\n📎 "
                            "پشتیبانی یک تصویر "
                            "ارسال کرده است."
                        )

                    keyboard = (
                        InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text=(
                                            "✍️ ارسال پاسخ"
                                        ),
                                        callback_data=(
                                            "ts:reply:"
                                            f"{ticket_id}"
                                        ),
                                    )
                                ]
                            ]
                        )
                        if ticket_id
                        else None
                    )

                # TWINPANEL_USER_NOTIFICATION_WORKER_V1
                elif (
                    row.kind
                    == "user_notification"
                ):
                    title = str(
                        payload.get("title")
                        or "اعلان"
                    ).strip()

                    body = str(
                        payload.get("message")
                        or ""
                    ).strip()

                    text = (
                        "🔔 <b>"
                        + escape(title)
                        + "</b>"
                    )

                    if body:
                        text += (
                            "\n\n"
                            + escape(body)
                        )

                    keyboard = None

                else:
                    row.delivered_at = (
                        datetime.utcnow()
                    )
                    db.commit()
                    continue

                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=text,
                        reply_markup=keyboard,
                    )

                    row.delivered_at = (
                        datetime.utcnow()
                    )

                    row.attempts += 1
                    row.last_error = None
                    db.commit()

                except Exception as exc:
                    row.attempts += 1
                    row.last_error = (
                        str(exc)[:1000]
                    )
                    db.commit()

        except Exception as exc:
            db.rollback()

            print(
                "telegram notification worker:",
                str(exc),
                flush=True,
            )

        finally:
            db.close()

        await asyncio.sleep(3)



async def main():
    if not BOT_SECRET:
        raise RuntimeError(
            "TWINPANEL_TELEGRAM_BOT_SECRET missing"
        )

    bot = Bot(
        token=load_bot_token(),
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        ),
    )

    dp = Dispatcher(
        storage=MemoryStorage()
    )

    # TWINPANEL_PURCHASE_ROUTER_V1
    # Purchase router must be before the main
    # router because main router has a generic
    # fallback message handler.
    from .telegram_purchase_bot import (
        create_purchase_router,
    )

    purchase_router = (
        create_purchase_router(
            request,
            session,
        )
    )

    dp.include_router(
        purchase_router
    )

    # TWINPANEL_GUIDES_WALLET_V1
    from .telegram_guides_bot import (
        create_guides_router,
    )
    from .telegram_wallet_bot import (
        create_wallet_router,
    )

    # TWINPANEL_MAIN_SHARED_LEARNING_ONLY_V1
    # آموزش و دانلود برنامه فقط از telegram_learning_center
    # مشترک با ربات نمایندگی مدیریت می‌شود.

    dp.include_router(
        create_wallet_router(
            request,
            session,
        )
    )

    # TWINPANEL_MAIN_SUPPORT_ROUTER_V1
    from .telegram_support_bot import (
        create_support_router,
    )

    dp.include_router(
        create_support_router(
            request,
        )
    )

    dp.include_router(router)

    await bot.delete_webhook(
        drop_pending_updates=False
    )

    notify_task = asyncio.create_task(
        _telegram_notification_worker(
            bot
        )
    )

    try:
        await dp.start_polling(bot)

    finally:
        notify_task.cancel()

        try:
            await notify_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
