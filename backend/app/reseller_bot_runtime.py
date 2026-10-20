import asyncio
import hashlib
import logging
import secrets
from datetime import datetime
from html import escape

from aiogram import (
    Bot,
    Dispatcher,
    F,
    Router,
)
from aiogram.client.default import (
    DefaultBotProperties,
)
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import (
    MemoryStorage,
)
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import (
    Subscription,
    User,
    UserRole,
)
from .models_reseller import (
    Reseller,
    ResellerBotSettings,
    ResellerCustomer,
    ResellerSubscription,
)
from .reseller_bot_crypto import (
    decrypt_bot_token,
)
from .reseller_telegram_models import (
    ResellerTelegramLink,
)
from .security import hash_password
from .telegram_learning_center import register_learning_handlers


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | %(levelname)s | "
        "%(message)s"
    ),
)

log = logging.getLogger(
    "twinpanel-reseller-bots"
)

POLL_INTERVAL = 6


# TWINPANEL_RESELLER_PURCHASE_STATE_V1
class ResellerPurchaseState(StatesGroup):
    # TWINPANEL_RESELLER_DISCOUNT_STATE_V1
    discount = State()
    proof = State()



def _status_value(value) -> str:
    return str(
        getattr(
            value,
            "value",
            value,
        )
        or ""
    ).lower()


def _brand(
    reseller: Reseller,
) -> str:
    return str(
        reseller.brand_name
        or reseller.name
        or f"نمایندگی {reseller.id}"
    ).strip()


def _main_keyboard():
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
                    text="🔄 تمدید اشتراک"
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
                KeyboardButton(
                    text="🎫 پشتیبانی"
                ),
            ],
        ],
    )


def _internal_email(
    reseller_id: int,
    telegram_id: int,
) -> str:
    return (
        f"tg-r{reseller_id}-"
        f"{telegram_id}"
        "@internal.twinpanel.invalid"
    )


def _display_name(tg_user) -> str:
    first = str(
        tg_user.first_name
        or ""
    ).strip()

    last = str(
        tg_user.last_name
        or ""
    ).strip()

    full = (
        f"{first} {last}"
    ).strip()

    if full:
        return full[:190]

    if tg_user.username:
        return (
            "@"
            + str(tg_user.username)
        )[:190]

    return (
        "کاربر تلگرام "
        + str(tg_user.id)
    )


# TWINPANEL_RESELLER_LINKED_USER_V1
def linked_user(
    db: Session,
    reseller_id: int,
    telegram_id: int,
) -> User | None:
    link = (
        db.query(ResellerTelegramLink)
        .filter(
            ResellerTelegramLink.reseller_id
            == reseller_id,
            ResellerTelegramLink.telegram_id
            == telegram_id,
        )
        .first()
    )

    if not link:
        return None

    user = db.get(
        User,
        int(link.user_id),
    )

    if not user or not user.is_active:
        return None

    return user


def _get_or_create_customer(
    db: Session,
    reseller_id: int,
    tg_user,
) -> tuple[
    User,
    ResellerTelegramLink,
    bool,
]:
    now = datetime.utcnow()

    link = (
        db.query(ResellerTelegramLink)
        .filter(
            ResellerTelegramLink.reseller_id
            == reseller_id,
            ResellerTelegramLink.telegram_id
            == int(tg_user.id),
        )
        .first()
    )

    if link:
        user = db.get(
            User,
            link.user_id,
        )

        if not user:
            db.delete(link)
            db.flush()
            link = None
        else:
            link.telegram_username = (
                tg_user.username
            )
            link.telegram_first_name = (
                tg_user.first_name
            )
            link.last_seen_at = now

            if not user.full_name:
                user.full_name = (
                    _display_name(tg_user)
                )

            db.commit()

            return (
                user,
                link,
                False,
            )

    email = _internal_email(
        reseller_id,
        int(tg_user.id),
    )

    user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    created = False

    if not user:
        user = User(
            email=email,
            phone=None,
            full_name=_display_name(
                tg_user
            ),
            password_hash=hash_password(
                secrets.token_urlsafe(32)
            ),
            role=UserRole.USER,
            is_active=True,
        )

        db.add(user)
        db.flush()
        created = True

    customer = (
        db.query(ResellerCustomer)
        .filter(
            ResellerCustomer.reseller_id
            == reseller_id,
            ResellerCustomer.user_id
            == user.id,
        )
        .first()
    )

    if not customer:
        db.add(
            ResellerCustomer(
                reseller_id=reseller_id,
                user_id=user.id,
            )
        )
        db.flush()

    link = ResellerTelegramLink(
        reseller_id=reseller_id,
        telegram_id=int(
            tg_user.id
        ),
        user_id=int(user.id),
        telegram_username=(
            tg_user.username
        ),
        telegram_first_name=(
            tg_user.first_name
        ),
        created_at=now,
        last_seen_at=now,
    )

    db.add(link)
    db.commit()
    db.refresh(link)

    return (
        user,
        link,
        created,
    )


def _customer(
    db: Session,
    reseller_id: int,
    telegram_id: int,
) -> User | None:
    link = (
        db.query(ResellerTelegramLink)
        .filter(
            ResellerTelegramLink.reseller_id
            == reseller_id,
            ResellerTelegramLink.telegram_id
            == telegram_id,
        )
        .first()
    )

    if not link:
        return None

    link.last_seen_at = (
        datetime.utcnow()
    )

    user = db.get(
        User,
        link.user_id,
    )

    db.commit()

    return user


def _subscriptions(
    db: Session,
    reseller_id: int,
    user_id: int,
):
    links = (
        db.query(
            ResellerSubscription
        )
        .filter(
            ResellerSubscription.reseller_id
            == reseller_id,
            ResellerSubscription.customer_user_id
            == user_id,
        )
        .order_by(
            ResellerSubscription.id.desc()
        )
        .all()
    )

    result = []

    for link in links:
        sub = db.get(
            Subscription,
            link.subscription_id,
        )

        if sub:
            result.append(
                (link, sub)
            )

    return result


def _days_left(sub) -> int:
    if not sub.expires_at:
        return 99999

    delta = (
        sub.expires_at
        - datetime.utcnow()
    )

    return max(
        0,
        int(
            delta.total_seconds()
            // 86400
        ),
    )


def _remaining_bytes(sub) -> int:
    total = int(
        sub.traffic_limit_bytes
        or 0
    )

    used = int(
        sub.traffic_used_bytes
        or 0
    )

    return max(
        0,
        total-used,
    )


def _gb(value) -> str:
    return (
        f"{int(value or 0)/(1024**3):.2f}"
        .rstrip("0")
        .rstrip(".")
    )


def _indicator(sub) -> str:
    status = _status_value(
        sub.status
    )

    if status != "active":
        return "🔴"

    days = _days_left(sub)

    total = int(
        sub.traffic_limit_bytes
        or 0
    )

    remaining = _remaining_bytes(
        sub
    )

    low_traffic = bool(
        total > 0
        and (
            remaining / total
        ) <= 0.10
    )

    if (
        days <= 3
        or low_traffic
    ):
        return "🟡"

    return "🟢"


def _status_fa(sub) -> str:
    return {
        "active": "فعال",
        "suspended": "معلق",
        "expired": "منقضی",
        "canceled": "لغو شده",
        "pending": "در انتظار",
    }.get(
        _status_value(sub.status),
        _status_value(sub.status)
        or "-",
    )


def _sub_username(sub) -> str:
    value = str(
        sub.account_username
        or ""
    ).strip()

    if value:
        return value

    return f"#{sub.id}"


def _subscription_buttons(
    rows,
):
    buttons = []

    for _, sub in rows:
        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"{_indicator(sub)} "
                    f"👤 {_sub_username(sub)}"
                ),
                callback_data=(
                    f"rsub:{sub.id}"
                ),
            )
        ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


def _subscription_detail_keyboard(
    sub_id: int,
    subscription_link: str | None,
):
    rows = []

    if subscription_link:
        rows.append([
            InlineKeyboardButton(
                text="🔗 اطلاعات اتصال",
                url=subscription_link,
            )
        ])

    rows.extend([
        [
            InlineKeyboardButton(
                text="🔄 تمدید",
                callback_data=(
                    f"rrenew:{sub_id}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="⬅️ اشتراک‌های من",
                callback_data=(
                    "rsubs:list"
                ),
            )
        ],
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def build_router(
    reseller_id: int,
) -> Router:
    router = Router(
        name=(
            f"reseller-bot-"
            f"{reseller_id}"
        )
    )
    # TWINPANEL_RESELLER_SHARED_LEARNING_V1
    register_learning_handlers(router, prefix="rlearn")



    @router.message(
        CommandStart()
    )
    async def start(
        message: Message,
    ):
        db = SessionLocal()

        try:
            reseller = db.get(
                Reseller,
                reseller_id,
            )

            settings = (
                db.query(
                    ResellerBotSettings
                )
                .filter(
                    ResellerBotSettings.reseller_id
                    == reseller_id
                )
                .first()
            )

            if (
                not reseller
                or not reseller.is_active
                or not settings
                or not settings.is_active
            ):
                await message.answer(
                    "این ربات در حال حاضر "
                    "فعال نیست."
                )
                return

            user, _, created = (
                _get_or_create_customer(
                    db,
                    reseller_id,
                    message.from_user,
                )
            )

            brand = _brand(
                reseller
            )

            if settings.welcome_message:
                welcome = (
                    settings.welcome_message
                )
            else:
                welcome = (
                    f"👋 به <b>"
                    f"{escape(brand)}"
                    f"</b> خوش آمدید."
                )

            if created:
                welcome += (
                    "\n\n✅ حساب کاربری شما "
                    "به‌صورت خودکار ایجاد شد."
                )

            await message.answer(
                welcome,
                reply_markup=_main_keyboard(),
            )

        except Exception:
            log.exception(
                "start failed reseller=%s",
                reseller_id,
            )

            await message.answer(
                "خطا در ارتباط با پنل."
            )

        finally:
            db.close()


    @router.message(
        F.text == "🏠 داشبورد"
    )
    async def dashboard(
        message: Message,
    ):
        db = SessionLocal()

        try:
            reseller = db.get(
                Reseller,
                reseller_id,
            )

            user = _customer(
                db,
                reseller_id,
                message.from_user.id,
            )

            if not user:
                await message.answer(
                    "ابتدا /start را ارسال کنید."
                )
                return

            rows = _subscriptions(
                db,
                reseller_id,
                user.id,
            )

            active = sum(
                1
                for _, sub in rows
                if _status_value(
                    sub.status
                ) == "active"
            )

            total_remaining = sum(
                _remaining_bytes(sub)
                for _, sub in rows
            )

            await message.answer(
                f"🏠 <b>{escape(_brand(reseller))}</b>\n\n"
                f"👤 {escape(user.full_name or '-')}\n"
                f"📦 تعداد اشتراک: <b>{len(rows)}</b>\n"
                f"🟢 اشتراک فعال: <b>{active}</b>\n"
                f"📊 حجم باقی‌مانده: "
                f"<b>{_gb(total_remaining)} GB</b>"
            )

        except Exception:
            log.exception(
                "dashboard failed reseller=%s",
                reseller_id,
            )

            await message.answer(
                "دریافت داشبورد ناموفق بود."
            )

        finally:
            db.close()


    async def send_subscriptions(
        target,
        telegram_id: int,
        *,
        edit=False,
    ):
        db = SessionLocal()

        try:
            user = _customer(
                db,
                reseller_id,
                telegram_id,
            )

            if not user:
                text = (
                    "ابتدا /start را "
                    "ارسال کنید."
                )

                if edit:
                    await target.edit_text(
                        text
                    )
                else:
                    await target.answer(
                        text
                    )

                return

            rows = _subscriptions(
                db,
                reseller_id,
                user.id,
            )

            if not rows:
                text = (
                    "📦 <b>اشتراک‌های من</b>\n\n"
                    "هنوز اشتراکی ندارید."
                )

                if edit:
                    await target.edit_text(
                        text
                    )
                else:
                    await target.answer(
                        text
                    )

                return

            text = (
                "📦 <b>اشتراک‌های من</b>\n\n"
                f"تعداد: <b>{len(rows)}</b>\n\n"
                "🟢 فعال   🟡 رو به اتمام   "
                "🔴 غیرفعال"
            )

            markup = (
                _subscription_buttons(
                    rows
                )
            )

            if edit:
                await target.edit_text(
                    text,
                    reply_markup=markup,
                )
            else:
                await target.answer(
                    text,
                    reply_markup=markup,
                )

        finally:
            db.close()


    @router.message(
        F.text == "📦 اشتراک‌های من"
    )
    async def subscriptions(
        message: Message,
    ):
        await send_subscriptions(
            message,
            message.from_user.id,
        )


    @router.callback_query(
        F.data == "rsubs:list"
    )
    async def subscriptions_callback(
        callback: CallbackQuery,
    ):
        await callback.answer()

        await send_subscriptions(
            callback.message,
            callback.from_user.id,
            edit=True,
        )


    @router.callback_query(
        F.data.startswith("rsub:")
    )
    async def subscription_detail(
        callback: CallbackQuery,
    ):
        sub_id = int(
            callback.data.split(
                ":",
                1,
            )[1]
        )

        db = SessionLocal()

        try:
            user = _customer(
                db,
                reseller_id,
                callback.from_user.id,
            )

            if not user:
                await callback.answer(
                    "حساب متصل نیست",
                    show_alert=True,
                )
                return

            link = (
                db.query(
                    ResellerSubscription
                )
                .filter(
                    ResellerSubscription.reseller_id
                    == reseller_id,
                    ResellerSubscription.customer_user_id
                    == user.id,
                    ResellerSubscription.subscription_id
                    == sub_id,
                )
                .first()
            )

            if not link:
                await callback.answer(
                    "اشتراک پیدا نشد",
                    show_alert=True,
                )
                return

            sub = db.get(
                Subscription,
                sub_id,
            )

            if not sub:
                await callback.answer(
                    "اشتراک پیدا نشد",
                    show_alert=True,
                )
                return

            # We only expose the safe share URL
            # and username, never raw protocol
            # credentials inside Telegram.
            from .routers.account_delivery import (
                _stored_info,
            )

            info = _stored_info(
                db,
                sub,
            )

            subscription_link = str(
                info.get(
                    "subscription_link"
                )
                or ""
            ).strip() or None

            username = str(
                (
                    info.get("account")
                    or {}
                ).get("username")
                or sub.account_username
                or "-"
            )

            limit = int(
                sub.traffic_limit_bytes
                or 0
            )

            used = int(
                sub.traffic_used_bytes
                or 0
            )

            remaining = max(
                0,
                limit-used,
            )

            expires = (
                sub.expires_at.strftime(
                    "%Y/%m/%d"
                )
                if sub.expires_at
                else "-"
            )

            await callback.answer()

            await callback.message.edit_text(
                f"{_indicator(sub)} "
                f"<b>مدیریت اشتراک</b>\n\n"

                f"👤 کاربری: "
                f"<code>{escape(username)}</code>\n"

                f"وضعیت: "
                f"<b>{escape(_status_fa(sub))}</b>\n"

                f"📅 انقضا: "
                f"<b>{expires}</b>\n"

                f"⏳ روز باقی‌مانده: "
                f"<b>{_days_left(sub)}</b>\n\n"

                f"📊 حجم کل: "
                f"<b>{_gb(limit)} GB</b>\n"

                f"📉 مصرف‌شده: "
                f"<b>{_gb(used)} GB</b>\n"

                f"📈 باقی‌مانده: "
                f"<b>{_gb(remaining)} GB</b>",
                reply_markup=(
                    _subscription_detail_keyboard(
                        sub.id,
                        subscription_link,
                    )
                ),
            )

        except Exception:
            log.exception(
                "subscription detail failed "
                "reseller=%s sub=%s",
                reseller_id,
                sub_id,
            )

            await callback.answer(
                "دریافت اطلاعات ناموفق بود",
                show_alert=True,
            )

        finally:
            db.close()


    @router.message(
        F.text == "🎫 پشتیبانی"
    )
    async def support(
        message: Message,
    ):
        db = SessionLocal()

        try:
            row = (
                db.query(
                    ResellerBotSettings
                )
                .filter(
                    ResellerBotSettings.reseller_id
                    == reseller_id
                )
                .first()
            )

            username = str(
                (
                    row.support_username
                    if row
                    else ""
                )
                or ""
            ).strip().lstrip("@")

            if not username:
                await message.answer(
                    "اطلاعات پشتیبانی "
                    "هنوز تنظیم نشده است."
                )
                return

            await message.answer(
                "🎫 <b>پشتیبانی</b>",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="💬 ارتباط با پشتیبانی",
                                url=(
                                    "https://t.me/"
                                    + username
                                ),
                            )
                        ]
                    ]
                ),
            )

        finally:
            db.close()


    @router.message(
        F.text == "🔄 تمدید اشتراک"
    )
    async def renew_menu(
        message: Message,
    ):
        await message.answer(
            "🔄 برای تمدید ابتدا وارد "
            "«اشتراک‌های من» شوید و کاربری "
            "موردنظر را انتخاب کنید."
        )


    # TWINPANEL_RESELLER_REAL_RENEWAL_V2
    def _renewal_context(
        db,
        telegram_id: int,
        subscription_id: int,
    ):
        from .models import (
            Plan,
            Subscription,
        )
        from .models_reseller import (
            Reseller,
            ResellerPlanPrice,
            ResellerSubscription,
        )

        user = linked_user(
            db,
            reseller_id,
            telegram_id,
        )

        if not user:
            raise ValueError(
                "ابتدا /start را ارسال کنید"
            )

        link = (
            db.query(ResellerSubscription)
            .filter(
                ResellerSubscription.reseller_id
                == reseller_id,
                ResellerSubscription.customer_user_id
                == user.id,
                ResellerSubscription.subscription_id
                == subscription_id,
            )
            .first()
        )

        if not link:
            raise ValueError(
                "اشتراک متعلق به این حساب نیست"
            )

        sub = db.get(
            Subscription,
            subscription_id,
        )

        if not sub:
            raise ValueError(
                "اشتراک پیدا نشد"
            )

        status = str(
            getattr(
                sub.status,
                "value",
                sub.status,
            )
        ).lower()

        if status in {
            "canceled",
            "pending",
        }:
            raise ValueError(
                "این اشتراک قابل تمدید نیست"
            )

        plan = db.get(
            Plan,
            sub.plan_id,
        )

        if (
            not plan
            or not plan.is_active
        ):
            raise ValueError(
                "پلن این اشتراک فعال نیست"
            )

        price = (
            db.query(ResellerPlanPrice)
            .filter(
                ResellerPlanPrice.reseller_id
                == reseller_id,
                ResellerPlanPrice.plan_id
                == plan.id,
                ResellerPlanPrice.is_active.is_(
                    True
                ),
            )
            .first()
        )

        if not price:
            raise ValueError(
                "قیمت نمایندگی این پلن فعال نیست"
            )

        reseller = db.get(
            Reseller,
            reseller_id,
        )

        if not reseller:
            raise ValueError(
                "نمایندگی پیدا نشد"
            )

        traffic_gb = int(
            plan.traffic_gb
            or 0
        )

        duration_days = int(
            plan.duration_days
            or 0
        )

        required_bytes = (
            traffic_gb
            * (1024 ** 3)
        )

        balance = int(
            reseller.traffic_balance_bytes
            or 0
        )

        credit = int(
            reseller.traffic_credit_bytes
            or 0
        )

        if (
            balance - required_bytes
            < -credit
        ):
            raise ValueError(
                "موجودی حجم نماینده برای تمدید کافی نیست"
            )

        protocols = [
            key
            for key, field in {
                "cisco": "enable_cisco",
                "openvpn": "enable_openvpn",
                "wireguard": "enable_wireguard",
                "l2tp": "enable_l2tp",
                "v2ray": "enable_v2ray",
            }.items()
            if bool(
                getattr(
                    plan,
                    field,
                    False,
                )
            )
        ]

        return {
            "user": user,
            "sub": sub,
            "plan": plan,
            "price": price,
            "reseller": reseller,
            "traffic_gb": traffic_gb,
            "duration_days": duration_days,
            "amount": int(
                price.sell_price_toman
                or 0
            ),
            "protocols": protocols,
        }


    def _renewal_order(
        db,
        context,
        telegram_id: int,
        payment_method_id,
    ):
        from .reseller_bot_order_models import (
            ResellerBotOrder,
        )

        sub = context["sub"]
        plan = context["plan"]
        user = context["user"]

        note = (
            f"renewal:{int(sub.id)}"
        )

        order = (
            db.query(ResellerBotOrder)
            .filter(
                ResellerBotOrder.reseller_id
                == reseller_id,
                ResellerBotOrder.customer_user_id
                == user.id,
                ResellerBotOrder.plan_id
                == plan.id,
                ResellerBotOrder.payment_note
                == note,
                ResellerBotOrder.status
                == "pending_payment",
            )
            .order_by(
                ResellerBotOrder.id.desc()
            )
            .first()
        )

        if not order:
            order = ResellerBotOrder(
                reseller_id=reseller_id,
                customer_user_id=user.id,
                telegram_id=telegram_id,
                plan_id=plan.id,
                payment_method_id=(
                    payment_method_id
                ),
                traffic_gb=context[
                    "traffic_gb"
                ],
                duration_days=context[
                    "duration_days"
                ],
                sell_price_toman=context[
                    "amount"
                ],
                base_sell_price_toman=context[
                    "amount"
                ],
                discount_amount_toman=0,
                protocols=context[
                    "protocols"
                ],
                node_ids=[],
                status="pending_payment",
                payment_note=note,
                sale_idempotency_key=(
                    f"tg-renew-"
                    f"{reseller_id}-"
                    f"{telegram_id}-"
                    f"{sub.id}-"
                    f"{secrets.token_hex(12)}"
                ),
            )

            db.add(order)

        else:
            order.payment_method_id = (
                payment_method_id
            )

            order.sell_price_toman = (
                context["amount"]
            )

            order.base_sell_price_toman = (
                context["amount"]
            )

            order.protocols = context[
                "protocols"
            ]

        db.commit()
        db.refresh(order)

        return order


    @router.callback_query(
        F.data.startswith("rrenew:")
    )
    async def renew_callback(
        callback: CallbackQuery,
    ):
        try:
            subscription_id = int(
                callback.data.split(
                    ":",
                    1,
                )[1]
            )
        except Exception:
            await callback.answer(
                "شناسه اشتراک معتبر نیست",
                show_alert=True,
            )
            return

        db = SessionLocal()

        try:
            from .models_reseller import (
                ResellerPaymentMethod,
            )

            context = _renewal_context(
                db,
                callback.from_user.id,
                subscription_id,
            )

            methods = (
                db.query(
                    ResellerPaymentMethod
                )
                .filter(
                    ResellerPaymentMethod.reseller_id
                    == reseller_id,
                    ResellerPaymentMethod.is_active.is_(
                        True
                    ),
                )
                .order_by(
                    ResellerPaymentMethod.id.asc()
                )
                .all()
            )

            rows = [[
                InlineKeyboardButton(
                    text="👛 کیف پول",
                    callback_data=(
                        f"rrenewwallet:"
                        f"{subscription_id}"
                    ),
                )
            ]]

            for method in methods:
                rows.append([
                    InlineKeyboardButton(
                        text=(
                            "💳 "
                            + str(
                                method.title
                                or "پرداخت"
                            )
                        ),
                        callback_data=(
                            f"rrenewpay:"
                            f"{subscription_id}:"
                            f"{method.id}"
                        ),
                    )
                ])

            rows.append([
                InlineKeyboardButton(
                    text="⬅️ بازگشت",
                    callback_data=(
                        f"rsub:{subscription_id}"
                    ),
                )
            ])

            await callback.answer()

            await callback.message.edit_text(
                "🔄 <b>تمدید اشتراک</b>\\n\\n"
                f"پلن: "
                f"<b>{escape(context['plan'].name)}</b>\\n"
                f"📊 حجم افزوده: "
                f"<b>{context['traffic_gb']} GB</b>\\n"
                f"📅 اعتبار افزوده: "
                f"<b>{context['duration_days']} روز</b>\\n"
                f"💰 مبلغ: "
                f"<b>{context['amount']:,} تومان</b>\\n\\n"
                "روش پرداخت را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=rows
                ),
            )

        except Exception as exc:
            await callback.answer(
                str(exc)[:180],
                show_alert=True,
            )

        finally:
            db.close()


    @router.callback_query(
        F.data.startswith(
            "rrenewwallet:"
        )
    )
    async def renewal_wallet_start(
        callback: CallbackQuery,
    ):
        subscription_id = int(
            callback.data.split(
                ":",
                1,
            )[1]
        )

        db = SessionLocal()

        try:
            from .routers.customer_wallet import (
                _wallet,
            )

            context = _renewal_context(
                db,
                callback.from_user.id,
                subscription_id,
            )

            order = _renewal_order(
                db,
                context,
                callback.from_user.id,
                None,
            )

            wallet = _wallet(
                db,
                context["user"].id,
            )

            db.refresh(wallet)

            balance = int(
                wallet.balance_toman
                or 0
            )

            amount = int(
                order.sell_price_toman
                or 0
            )

            remaining = (
                balance
                - amount
            )

            buttons = []

            if remaining >= 0:
                buttons.append([
                    InlineKeyboardButton(
                        text="✅ پرداخت و تمدید",
                        callback_data=(
                            f"rwalletpay:"
                            f"{order.id}"
                        ),
                    )
                ])

            buttons.append([
                InlineKeyboardButton(
                    text="⬅️ بازگشت",
                    callback_data=(
                        f"rrenew:"
                        f"{subscription_id}"
                    ),
                )
            ])

            status_text = (
                "✅ موجودی کیف پول کافی است."
                if remaining >= 0
                else
                "❌ موجودی کیف پول کافی نیست."
            )

            await callback.answer()

            await callback.message.edit_text(
                "👛 <b>پرداخت تمدید از کیف پول</b>\\n\\n"
                f"📊 حجم افزوده: "
                f"<b>{context['traffic_gb']} GB</b>\\n"
                f"📅 اعتبار افزوده: "
                f"<b>{context['duration_days']} روز</b>\\n\\n"
                f"👛 موجودی: "
                f"<b>{balance:,} تومان</b>\\n"
                f"💰 مبلغ تمدید: "
                f"<b>{amount:,} تومان</b>\\n"
                f"💵 مانده بعد از پرداخت: "
                f"<b>{max(remaining, 0):,} تومان</b>\\n\\n"
                f"{status_text}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=buttons
                ),
            )

        except Exception as exc:
            db.rollback()

            await callback.answer(
                str(exc)[:180],
                show_alert=True,
            )

        finally:
            db.close()


    @router.callback_query(
        F.data.startswith(
            "rrenewpay:"
        )
    )
    async def renewal_manual_payment(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        parts = callback.data.split(":")

        if len(parts) != 3:
            await callback.answer(
                "اطلاعات پرداخت معتبر نیست",
                show_alert=True,
            )
            return

        subscription_id = int(parts[1])
        method_id = int(parts[2])

        db = SessionLocal()

        try:
            from .models_reseller import (
                ResellerPaymentMethod,
            )

            context = _renewal_context(
                db,
                callback.from_user.id,
                subscription_id,
            )

            method = (
                db.query(
                    ResellerPaymentMethod
                )
                .filter(
                    ResellerPaymentMethod.id
                    == method_id,
                    ResellerPaymentMethod.reseller_id
                    == reseller_id,
                    ResellerPaymentMethod.is_active.is_(
                        True
                    ),
                )
                .first()
            )

            if not method:
                await callback.answer(
                    "روش پرداخت معتبر نیست",
                    show_alert=True,
                )
                return

            order = _renewal_order(
                db,
                context,
                callback.from_user.id,
                method.id,
            )

            await state.set_state(
                ResellerPurchaseState.proof
            )

            await state.update_data(
                order_id=int(order.id)
            )

            title = (
                method.title
                or "پرداخت"
            )

            lines = [
                "🔄 <b>پرداخت تمدید اشتراک</b>",
                "",
                f"شماره سفارش: "
                f"<b>#{order.id}</b>",
                f"روش: "
                f"<b>{escape(title)}</b>",
                f"مبلغ: "
                f"<b>{int(order.sell_price_toman):,} تومان</b>",
            ]

            if method.card_number:
                lines.extend([
                    "",
                    "شماره کارت:",
                    f"<code>{escape(method.card_number)}</code>",
                ])

            if method.iban:
                lines.extend([
                    "",
                    "شماره شبا:",
                    f"<code>{escape(method.iban)}</code>",
                ])

            if method.account_holder:
                lines.append(
                    "به نام: "
                    f"<b>{escape(method.account_holder)}</b>"
                )

            if method.instructions:
                lines.extend([
                    "",
                    escape(
                        method.instructions
                    ),
                ])

            lines.extend([
                "",
                "بعد از پرداخت، "
                "<b>کد پیگیری یا تصویر رسید</b> "
                "را همین‌جا ارسال کنید.",
            ])

            await callback.answer()

            await callback.message.edit_text(
                "\\n".join(lines)
            )

        except Exception as exc:
            db.rollback()

            await callback.answer(
                str(exc)[:180],
                show_alert=True,
            )

        finally:
            db.close()


    @router.message(
        F.text == "🛒 خرید اشتراک"
    )
    async def purchase(
        message: Message,
    ):
        db = SessionLocal()

        try:
            from .models_reseller import (
                ResellerPlanPrice,
            )
            from .models import Plan

            prices = (
                db.query(
                    ResellerPlanPrice
                )
                .filter(
                    ResellerPlanPrice.reseller_id
                    == reseller_id,
                    ResellerPlanPrice.is_active.is_(
                        True
                    ),
                )
                .order_by(
                    ResellerPlanPrice.id.desc()
                )
                .all()
            )

            rows = []

            for price in prices:
                plan = db.get(
                    Plan,
                    price.plan_id,
                )

                if not plan or not plan.is_active:
                    continue

                rows.append(
                    [
                        InlineKeyboardButton(
                            text=(
                                f"{plan.name} • "
                                f"{int(price.sell_price_toman):,} تومان"
                            ),
                            callback_data=(
                                "rbuy:"
                                f"{plan.id}"
                            ),
                        )
                    ]
                )

            if not rows:
                await message.answer(
                    "در حال حاضر پلن فعالی "
                    "برای فروش وجود ندارد."
                )
                return

            await message.answer(
                "🛒 <b>خرید اشتراک</b>\n\n"
                "پلن موردنظر را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=rows
                ),
            )

        finally:
            db.close()


    # TWINPANEL_RESELLER_BOT_PAYMENT_FLOW_V1

    @router.callback_query(
        F.data.startswith("rbuy:")
    )
    async def purchase_plan(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        plan_id=int(
            callback.data.split(":")[1]
        )

        db=SessionLocal()

        try:
            from .models_reseller import (
                ResellerPaymentMethod,
                ResellerPlanPrice,
            )
            from .models import Plan

            price=(
                db.query(ResellerPlanPrice)
                .filter(
                    ResellerPlanPrice.reseller_id
                    == reseller_id,
                    ResellerPlanPrice.plan_id
                    == plan_id,
                    ResellerPlanPrice.is_active.is_(True),
                )
                .first()
            )

            plan=db.get(
                Plan,
                plan_id,
            )

            if not price or not plan:
                await callback.answer(
                    "پلن پیدا نشد",
                    show_alert=True,
                )
                return

            # TWINPANEL_RESELLER_DISCOUNT_PAYMENT_UI_V1
            state_data=await state.get_data()

            discount_applied=(
                int(
                    state_data.get(
                        "discount_plan_id"
                    )
                    or 0
                )
                == int(plan_id)
                and bool(
                    state_data.get(
                        "discount_code"
                    )
                )
            )

            base_amount=int(
                price.sell_price_toman
                or 0
            )

            if discount_applied:
                discount_amount=int(
                    state_data.get(
                        "discount_amount_toman"
                    )
                    or 0
                )

                final_amount=int(
                    state_data.get(
                        "discount_final_toman"
                    )
                    or base_amount
                )

                price_text=(
                    f"💰 قیمت اصلی: "
                    f"<b>{base_amount:,} تومان</b>\n"
                    f"🎁 تخفیف: "
                    f"<b>{discount_amount:,} تومان</b>\n"
                    f"✅ مبلغ نهایی: "
                    f"<b>{final_amount:,} تومان</b>"
                )

            else:
                price_text=(
                    f"💰 مبلغ: "
                    f"<b>{base_amount:,} تومان</b>"
                )

            methods=(
                db.query(ResellerPaymentMethod)
                .filter(
                    ResellerPaymentMethod.reseller_id
                    == reseller_id,
                    ResellerPaymentMethod.is_active.is_(True),
                )
                .order_by(
                    ResellerPaymentMethod.id.asc()
                )
                .all()
            )

            buttons=[]

            buttons.append([
                InlineKeyboardButton(
                    text=(
                        "🎟 تغییر کد تخفیف"
                        if discount_applied
                        else "🎟 اعمال کد تخفیف"
                    ),
                    callback_data=(
                        f"rdiscount:{plan_id}"
                    ),
                )
            ])

            for method in methods:
                title=(
                    method.title
                    or (
                        "کارت به کارت"
                        if method.method_type
                        == "card_to_card"
                        else method.method_type
                    )
                )

                buttons.append([
                    InlineKeyboardButton(
                        text=f"💳 {title}",
                        callback_data=(
                            f"rpay:{plan_id}:"
                            f"{method.id}"
                        ),
                    )
                ])

            # TWINPANEL_RESELLER_WALLET_PAYMENT_BUTTON_V1
            buttons.append([
                InlineKeyboardButton(
                    text="👛 کیف پول",
                    callback_data=(
                        f"rwallet:{plan_id}"
                    ),
                )
            ])

            await callback.answer()

            await callback.message.edit_text(
                f"🛒 <b>{escape(plan.name)}</b>\n\n"
                f"📊 حجم: <b>{plan.traffic_gb} GB</b>\n"
                f"📅 اعتبار: <b>{plan.duration_days} روز</b>\n"
                f"📱 دستگاه: <b>{plan.device_limit}</b>\n"
                f"{price_text}\n\n"
                "روش پرداخت را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=buttons
                ),
            )

        finally:
            db.close()


    # TWINPANEL_RESELLER_WALLET_PURCHASE_V1

    @router.callback_query(
        F.data.startswith("rwallet:")
    )
    async def wallet_purchase_preview(
        callback: CallbackQuery,
    ):
        plan_id=int(
            callback.data.split(":")[1]
        )

        db=SessionLocal()

        try:
            from .models import Plan
            from .models_reseller import (
                ResellerPlanPrice,
            )
            from .reseller_bot_order_models import (
                ResellerBotOrder,
            )
            from .routers.customer_wallet import (
                _wallet,
            )

            user=linked_user(
                db,
                reseller_id,
                callback.from_user.id,
            )

            if not user:
                await callback.answer(
                    "ابتدا /start را ارسال کنید",
                    show_alert=True,
                )
                return

            plan=db.get(
                Plan,
                plan_id,
            )

            price=(
                db.query(ResellerPlanPrice)
                .filter(
                    ResellerPlanPrice.reseller_id
                    == reseller_id,
                    ResellerPlanPrice.plan_id
                    == plan_id,
                    ResellerPlanPrice.is_active.is_(True),
                )
                .first()
            )

            if not plan or not price:
                await callback.answer(
                    "پلن معتبر نیست",
                    show_alert=True,
                )
                return

            protocols=[
                key
                for key,field in {
                    "cisco":"enable_cisco",
                    "openvpn":"enable_openvpn",
                    "wireguard":"enable_wireguard",
                    "l2tp":"enable_l2tp",
                    "v2ray":"enable_v2ray",
                }.items()
                if bool(
                    getattr(
                        plan,
                        field,
                        False,
                    )
                )
            ]

            if not protocols:
                await callback.answer(
                    "این پلن پروتکل فعالی ندارد",
                    show_alert=True,
                )
                return

            # سفارش پرداخت‌نشده قبلی کیف پول
            # را دوباره استفاده می‌کنیم.
            order=(
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.reseller_id
                    == reseller_id,
                    ResellerBotOrder.customer_user_id
                    == user.id,
                    ResellerBotOrder.plan_id
                    == plan.id,
                    ResellerBotOrder.payment_method_id.is_(None),
                    ResellerBotOrder.payment_note
                    == "wallet",
                    ResellerBotOrder.status
                    == "pending_payment",
                )
                .order_by(
                    ResellerBotOrder.id.desc()
                )
                .first()
            )

            if not order:
                order=ResellerBotOrder(
                    reseller_id=reseller_id,
                    customer_user_id=user.id,
                    telegram_id=(
                        callback.from_user.id
                    ),
                    plan_id=plan.id,
                    payment_method_id=None,
                    traffic_gb=int(
                        plan.traffic_gb
                    ),
                    duration_days=int(
                        plan.duration_days
                    ),
                    sell_price_toman=int(
                        price.sell_price_toman
                    ),
                    protocols=protocols,
                    node_ids=[],
                    status="pending_payment",
                    payment_note="wallet",
                    sale_idempotency_key=(
                        f"tg-wallet-sale-"
                        f"{reseller_id}-"
                        f"{callback.from_user.id}-"
                        f"{secrets.token_hex(12)}"
                    ),
                )

                db.add(order)

            else:
                order.sell_price_toman=int(
                    price.sell_price_toman
                )
                order.protocols=protocols

            wallet=_wallet(
                db,
                user.id,
            )

            db.commit()
            db.refresh(order)
            db.refresh(wallet)

            balance=int(
                wallet.balance_toman or 0
            )

            amount=int(
                order.sell_price_toman
            )

            remaining=balance-amount

            buttons=[]

            if remaining>=0:
                buttons.append([
                    InlineKeyboardButton(
                        text="✅ پرداخت و ساخت اشتراک",
                        callback_data=(
                            f"rwalletpay:{order.id}"
                        ),
                    )
                ])

            buttons.append([
                InlineKeyboardButton(
                    text="💳 روش‌های دیگر",
                    callback_data=(
                        f"rbuy:{plan.id}"
                    ),
                )
            ])

            if remaining>=0:
                status_text=(
                    "✅ موجودی برای خرید کافی است."
                )
            else:
                status_text=(
                    "❌ موجودی کیف پول کافی نیست.\n"
                    f"کسری: <b>{abs(remaining):,} تومان</b>"
                )

            await callback.answer()

            await callback.message.edit_text(
                "👛 <b>پرداخت از کیف پول</b>\n\n"
                f"🛒 پلن: <b>{escape(plan.name)}</b>\n"
                f"📊 حجم: <b>{plan.traffic_gb} GB</b>\n"
                f"📅 اعتبار: <b>{plan.duration_days} روز</b>\n\n"
                f"👛 موجودی: <b>{balance:,} تومان</b>\n"
                f"💰 مبلغ خرید: <b>{amount:,} تومان</b>\n"
                f"💵 مانده بعد از خرید: "
                f"<b>{max(remaining,0):,} تومان</b>\n\n"
                f"{status_text}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=buttons
                ),
            )

        finally:
            db.close()


    @router.callback_query(
        F.data.startswith("rwalletpay:")
    )
    async def wallet_purchase_pay(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        from datetime import datetime

        order_id=int(
            callback.data.split(":")[1]
        )

        db=SessionLocal()

        try:
            from .customer_wallet_models import (
                CustomerWalletTransaction,
            )
            from .models import (
                Subscription,
            )
            from .models_reseller import (
                Reseller,
            )
            from .reseller_bot_order_models import (
                ResellerBotOrder,
            )
            from .routers.account_delivery import (
                _stored_info,
            )
            from .routers.customer_wallet import (
                _wallet,
            )
            from .routers.reseller_bot_orders import (
                approve_order,
            )

            user=linked_user(
                db,
                reseller_id,
                callback.from_user.id,
            )

            if not user:
                await callback.answer(
                    "ابتدا /start را ارسال کنید",
                    show_alert=True,
                )
                return

            reseller=db.get(
                Reseller,
                reseller_id,
            )

            if not reseller:
                await callback.answer(
                    "نمایندگی پیدا نشد",
                    show_alert=True,
                )
                return

            # قفل سفارش:
            # دوبار زدن دکمه نمی‌تواند
            # دو پرداخت همزمان ایجاد کند.
            order=(
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.id
                    == order_id,
                    ResellerBotOrder.reseller_id
                    == reseller_id,
                    ResellerBotOrder.customer_user_id
                    == user.id,
                    ResellerBotOrder.payment_method_id.is_(
                        None
                    ),
                )
                .with_for_update()
                .first()
            )

            if not order:
                await callback.answer(
                    "سفارش پیدا نشد",
                    show_alert=True,
                )
                return

            # اگر قبلاً کامل شده، دوباره پول کم نشود.
            if order.status=="fulfilled":
                sub=(
                    db.get(
                        Subscription,
                        order.subscription_id,
                    )
                    if order.subscription_id
                    else None
                )

                info=(
                    _stored_info(db,sub)
                    if sub else {}
                )

                link=(
                    info.get(
                        "subscription_link"
                    )
                    if info else None
                )

                username=(
                    (
                        info.get("account")
                        or {}
                    ).get("username")
                    if info else None
                )

                lines=[
                    "✅ <b>این سفارش قبلاً پرداخت و فعال شده است.</b>",
                ]

                if username:
                    lines.append(
                        f"👤 نام کاربری: "
                        f"<code>{escape(username)}</code>"
                    )

                if link:
                    lines.extend([
                        "",
                        "🔗 لینک اتصال:",
                        f"<code>{escape(link)}</code>",
                    ])

                await callback.answer()

                await callback.message.edit_text(
                    "\n".join(lines)
                )

                await state.clear()
                return

            if order.status=="provisioning":
                await callback.answer(
                    "اشتراک در حال ساخت است",
                    show_alert=True,
                )
                return

            if order.status not in {
                "pending_payment",
                "awaiting_review",
                "provision_failed",
            }:
                await callback.answer(
                    "وضعیت سفارش معتبر نیست",
                    show_alert=True,
                )
                return

            # قبل از برداشت پول،
            # موجودی حجمی نماینده کنترل شود.
            required_bytes=(
                int(order.traffic_gb)
                * (1024 ** 3)
            )

            reseller_traffic=int(
                reseller.traffic_balance_bytes
                or 0
            )

            if (
                not order.subscription_id
                and reseller_traffic
                < required_bytes
            ):
                await callback.answer(
                    "موجودی حجم نماینده کافی نیست",
                    show_alert=True,
                )
                return

            wallet=_wallet(
                db,
                user.id,
                lock=True,
            )

            amount=int(
                order.sell_price_toman
            )

            reference=(
                f"reseller-bot-wallet-order:"
                f"{order.id}"
            )

            previous_tx=(
                db.query(
                    CustomerWalletTransaction
                )
                .filter(
                    CustomerWalletTransaction.user_id
                    == user.id,
                    CustomerWalletTransaction.reference
                    == reference,
                )
                .first()
            )

            # فقط اگر قبلاً برای این سفارش
            # تراکنشی ثبت نشده باشد برداشت می‌کنیم.
            if not previous_tx:
                balance=int(
                    wallet.balance_toman or 0
                )

                if balance<amount:
                    db.rollback()

                    await callback.answer(
                        "موجودی کیف پول کافی نیست",
                        show_alert=True,
                    )
                    return

                wallet.balance_toman=(
                    balance-amount
                )

                wallet.updated_at=(
                    datetime.utcnow()
                )

                db.add(
                    CustomerWalletTransaction(
                        user_id=user.id,
                        amount_toman=-amount,
                        kind="purchase",
                        description=(
                            "خرید اشتراک از ربات نماینده "
                            f"#{order.id}"
                        ),
                        reference=reference,
                    )
                )

                if not str(
                    order.payment_note
                    or ""
                ).startswith("renewal:"):
                    order.payment_note="wallet"

                order.status="awaiting_review"

                if not order.submitted_at:
                    order.submitted_at=(
                        datetime.utcnow()
                    )

                db.commit()

            elif order.status=="pending_payment":
                # تراکنش ثبت شده ولی اجرای سفارش
                # قبلی نیمه‌کاره مانده است.
                order.status="awaiting_review"

                if not order.submitted_at:
                    order.submitted_at=(
                        datetime.utcnow()
                    )

                db.commit()

            await callback.answer(
                "پرداخت انجام شد؛ در حال ساخت اشتراک..."
            )

            await callback.message.edit_text(
                "✅ <b>پرداخت از کیف پول انجام شد.</b>\n\n"
                "⏳ در حال ساخت اشتراک..."
            )

            try:
                result=await approve_order(
                    order.id,
                    reseller=reseller,
                    db=db,
                )

            except Exception as exc:
                detail=getattr(
                    exc,
                    "detail",
                    str(exc),
                )

                await callback.message.edit_text(
                    "✅ مبلغ از کیف پول پرداخت شده است.\n\n"
                    "⚠️ ساخت اشتراک کامل نشد.\n"
                    "می‌توانید دوباره تلاش کنید؛ "
                    "مبلغ دوباره از کیف پول کم نمی‌شود.\n\n"
                    f"خطا: <code>{escape(str(detail)[:700])}</code>",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(
                                text="🔄 تلاش مجدد",
                                callback_data=(
                                    f"rwalletpay:{order.id}"
                                ),
                            )
                        ]]
                    ),
                )

                return

            delivery=(
                result.get("delivery")
                or {}
            )

            username=delivery.get(
                "username"
            )

            link=delivery.get(
                "subscription_link"
            )

            # موجودی جدید
            wallet=_wallet(
                db,
                user.id,
            )

            balance_after=int(
                wallet.balance_toman or 0
            )

            lines=[
                "✅ <b>خرید با موفقیت انجام شد.</b>",
                "",
                f"💰 مبلغ: <b>{amount:,} تومان</b>",
                f"👛 موجودی کیف پول: "
                f"<b>{balance_after:,} تومان</b>",
            ]

            if username:
                lines.extend([
                    "",
                    "👤 نام کاربری:",
                    f"<code>{escape(username)}</code>",
                ])

            if link:
                lines.extend([
                    "",
                    "🔗 لینک اتصال:",
                    f"<code>{escape(link)}</code>",
                ])

            await callback.message.edit_text(
                "\n".join(lines)
            )

            await state.clear()

        finally:
            db.close()


    # TWINPANEL_RESELLER_DISCOUNT_HANDLERS_V1

    @router.callback_query(
        F.data.startswith("rdiscount:")
    )
    async def start_discount_code(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        plan_id=int(
            callback.data.split(":")[1]
        )

        await state.set_state(
            ResellerPurchaseState.discount
        )

        await state.update_data(
            discount_plan_id=plan_id
        )

        await callback.answer()

        await callback.message.edit_text(
            "🎟 <b>کد تخفیف</b>\n\n"
            "کد تخفیف را ارسال کنید."
        )


    @router.message(
        ResellerPurchaseState.discount
    )
    async def receive_discount_code(
        message: Message,
        state: FSMContext,
    ):
        code=str(
            message.text or ""
        ).strip()

        if not code:
            await message.answer(
                "کد تخفیف را ارسال کنید."
            )
            return

        state_data=await state.get_data()

        plan_id=int(
            state_data.get(
                "discount_plan_id"
            )
            or 0
        )

        if not plan_id:
            await state.clear()

            await message.answer(
                "پلن خرید پیدا نشد."
            )
            return

        db=SessionLocal()

        try:
            from .discount_service import (
                evaluate_discount,
            )

            from .models import Plan

            from .models_reseller import (
                ResellerPlanPrice,
            )

            user=linked_user(
                db,
                reseller_id,
                message.from_user.id,
            )

            if not user:
                await state.clear()

                await message.answer(
                    "حساب کاربری پیدا نشد."
                )
                return

            plan=db.get(
                Plan,
                plan_id,
            )

            price=(
                db.query(
                    ResellerPlanPrice
                )
                .filter(
                    ResellerPlanPrice.reseller_id
                    == reseller_id,
                    ResellerPlanPrice.plan_id
                    == plan_id,
                    ResellerPlanPrice.is_active
                    .is_(True),
                )
                .first()
            )

            if not plan or not price:
                await state.clear()

                await message.answer(
                    "پلن فعال پیدا نشد."
                )
                return

            result=evaluate_discount(
                db,
                owner_type="reseller",
                reseller_id=reseller_id,
                user_id=user.id,
                code=code,
                plan_id=plan.id,
                base_amount_toman=int(
                    price.sell_price_toman
                    or 0
                ),
                purpose="purchase",
            )

            await state.update_data(
                discount_plan_id=plan.id,
                discount_code=result[
                    "code"
                ],
                discount_amount_toman=int(
                    result[
                        "discount_amount_toman"
                    ]
                ),
                discount_final_toman=int(
                    result[
                        "final_amount_toman"
                    ]
                ),
            )

            # Keep discount data but leave
            # the text-input state.
            await state.set_state(None)

            await message.answer(
                "✅ <b>کد تخفیف اعمال شد.</b>\n\n"
                f"🎟 کد: "
                f"<code>{escape(result['code'])}</code>\n"
                f"💰 قیمت اصلی: "
                f"<b>{int(result['base_amount_toman']):,} تومان</b>\n"
                f"🎁 تخفیف: "
                f"<b>{int(result['discount_amount_toman']):,} تومان</b>\n"
                f"✅ مبلغ نهایی: "
                f"<b>{int(result['final_amount_toman']):,} تومان</b>",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ ادامه پرداخت",
                                callback_data=(
                                    f"rbuy:{plan.id}"
                                ),
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="❌ حذف کد تخفیف",
                                callback_data=(
                                    f"rdiscountremove:{plan.id}"
                                ),
                            )
                        ],
                    ]
                ),
            )

        except Exception as exc:
            detail=getattr(
                exc,
                "detail",
                str(exc),
            )

            await message.answer(
                "❌ کد تخفیف اعمال نشد.\n\n"
                f"{escape(str(detail))}"
            )

        finally:
            db.close()


    @router.callback_query(
        F.data.startswith(
            "rdiscountremove:"
        )
    )
    async def remove_discount_code(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        plan_id=int(
            callback.data.split(":")[1]
        )

        await state.update_data(
            discount_plan_id=None,
            discount_code=None,
            discount_amount_toman=0,
            discount_final_toman=0,
        )

        await state.set_state(None)

        await callback.answer(
            "کد تخفیف حذف شد"
        )

        await callback.message.edit_text(
            "کد تخفیف حذف شد.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="ادامه خرید",
                        callback_data=(
                            f"rbuy:{plan_id}"
                        ),
                    )
                ]]
            ),
        )


    @router.callback_query(
        F.data.startswith("rpay:")
    )
    async def select_payment_method(
        callback: CallbackQuery,
        state: FSMContext,
    ):
        _,plan_raw,method_raw=(
            callback.data.split(":")
        )

        plan_id=int(plan_raw)
        method_id=int(method_raw)

        db=SessionLocal()

        try:
            from .models_reseller import (
                ResellerPaymentMethod,
                ResellerPlanPrice,
            )
            from .models import Plan
            from .reseller_bot_order_models import (
                ResellerBotOrder,
            )

            user=linked_user(
                db,
                reseller_id,
                callback.from_user.id,
            )

            if not user:
                await callback.answer(
                    "ابتدا /start را ارسال کنید",
                    show_alert=True,
                )
                return

            plan=db.get(
                Plan,
                plan_id,
            )

            price=(
                db.query(ResellerPlanPrice)
                .filter(
                    ResellerPlanPrice.reseller_id
                    == reseller_id,
                    ResellerPlanPrice.plan_id
                    == plan_id,
                    ResellerPlanPrice.is_active.is_(True),
                )
                .first()
            )

            method=(
                db.query(ResellerPaymentMethod)
                .filter(
                    ResellerPaymentMethod.id
                    == method_id,
                    ResellerPaymentMethod.reseller_id
                    == reseller_id,
                    ResellerPaymentMethod.is_active.is_(True),
                )
                .first()
            )

            if not plan or not price or not method:
                await callback.answer(
                    "اطلاعات خرید معتبر نیست",
                    show_alert=True,
                )
                return

            protocols=[
                key
                for key,field in {
                    "cisco":"enable_cisco",
                    "openvpn":"enable_openvpn",
                    "wireguard":"enable_wireguard",
                    "l2tp":"enable_l2tp",
                    "v2ray":"enable_v2ray",
                }.items()
                if bool(
                    getattr(
                        plan,
                        field,
                        False,
                    )
                )
            ]

            if not protocols:
                await callback.answer(
                    "این پلن پروتکل فعالی ندارد",
                    show_alert=True,
                )
                return

            # Reuse an unfinished order instead
            # of creating duplicates on double-click.
            order=(
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.reseller_id
                    == reseller_id,
                    ResellerBotOrder.customer_user_id
                    == user.id,
                    ResellerBotOrder.plan_id
                    == plan.id,
                    ResellerBotOrder.status
                    == "pending_payment",
                )
                .order_by(
                    ResellerBotOrder.id.desc()
                )
                .first()
            )

            if not order:
                order=ResellerBotOrder(
                    reseller_id=reseller_id,
                    customer_user_id=user.id,
                    telegram_id=(
                        callback.from_user.id
                    ),
                    plan_id=plan.id,
                    payment_method_id=method.id,
                    traffic_gb=int(
                        plan.traffic_gb
                    ),
                    duration_days=int(
                        plan.duration_days
                    ),
                    sell_price_toman=int(
                        price.sell_price_toman
                    ),
                    protocols=protocols,
                    node_ids=[],
                    status="pending_payment",
                    sale_idempotency_key=(
                        f"tg-sale-{reseller_id}-"
                        f"{callback.from_user.id}-"
                        f"{secrets.token_hex(12)}"
                    ),
                )

                db.add(order)
            else:
                order.payment_method_id=(
                    method.id
                )
                order.sell_price_toman=int(
                    price.sell_price_toman
                )
                order.protocols=protocols

            db.commit()
            db.refresh(order)

            # TWINPANEL_RESELLER_ORDER_DISCOUNT_APPLY_V1
            from datetime import datetime as _dt

            from .discount_service import (
                release_discount_for_order,
                reserve_discount_for_order,
            )

            state_data=await state.get_data()

            current_base=int(
                price.sell_price_toman
                or 0
            )

            discount_code=(
                state_data.get(
                    "discount_code"
                )
                if int(
                    state_data.get(
                        "discount_plan_id"
                    )
                    or 0
                )
                == int(plan.id)
                else None
            )

            if discount_code:
                result=reserve_discount_for_order(
                    db,
                    owner_type="reseller",
                    reseller_id=reseller_id,
                    user_id=user.id,
                    code=str(
                        discount_code
                    ),
                    plan_id=plan.id,
                    base_amount_toman=
                        current_base,
                    purpose="purchase",
                    order_kind="reseller_bot",
                    order_id=order.id,
                )

                order.base_sell_price_toman=(
                    int(
                        result[
                            "base_amount_toman"
                        ]
                    )
                )

                order.discount_code_id=(
                    int(
                        result[
                            "discount_code_id"
                        ]
                    )
                )

                order.discount_code_snapshot=(
                    str(result["code"])
                )

                order.discount_amount_toman=(
                    int(
                        result[
                            "discount_amount_toman"
                        ]
                    )
                )

                # sell_price_toman is final payable.
                order.sell_price_toman=(
                    int(
                        result[
                            "final_amount_toman"
                        ]
                    )
                )

                order.discount_applied_at=(
                    _dt.utcnow()
                )

            else:
                release_discount_for_order(
                    db,
                    order_kind="reseller_bot",
                    order_id=order.id,
                )

                order.base_sell_price_toman=(
                    current_base
                )

                order.sell_price_toman=(
                    current_base
                )

                order.discount_code_id=None
                order.discount_code_snapshot=None
                order.discount_amount_toman=0
                order.discount_applied_at=None

            db.commit()
            db.refresh(order)

            await state.set_state(
                ResellerPurchaseState.proof
            )

            await state.update_data(
                order_id=int(order.id)
            )

            title=(
                method.title
                or "کارت به کارت"
            )

            lines=[
                "💳 <b>پرداخت سفارش</b>",
                "",
                f"شماره سفارش: <b>#{order.id}</b>",
                f"روش: <b>{escape(title)}</b>",
                f"مبلغ: <b>{int(order.sell_price_toman):,} تومان</b>",
            ]

            if method.card_number:
                lines.extend([
                    "",
                    "شماره کارت:",
                    f"<code>{escape(method.card_number)}</code>",
                ])

            if method.iban:
                lines.extend([
                    "",
                    "شماره شبا:",
                    f"<code>{escape(method.iban)}</code>",
                ])

            if method.account_holder:
                lines.append(
                    "به نام: "
                    f"<b>{escape(method.account_holder)}</b>"
                )

            if method.instructions:
                lines.extend([
                    "",
                    escape(
                        method.instructions
                    ),
                ])

            lines.extend([
                "",
                "بعد از پرداخت، "
                "<b>کد پیگیری یا تصویر رسید</b> "
                "را همین‌جا ارسال کنید.",
            ])

            await callback.answer()

            await callback.message.edit_text(
                "\n".join(lines)
            )

        finally:
            db.close()


    @router.message(
        ResellerPurchaseState.proof
    )
    async def receive_payment_proof(
        message: Message,
        state: FSMContext,
    ):
        data=await state.get_data()

        order_id=int(
            data.get("order_id") or 0
        )

        if not order_id:
            await state.clear()

            await message.answer(
                "سفارش پرداخت پیدا نشد؛ "
                "خرید را دوباره شروع کنید."
            )
            return

        text=(
            message.text
            or message.caption
            or ""
        ).strip()

        # TWINPANEL_RESELLER_RECEIPT_DOCUMENT_V1
        photo_file_id=None

        if message.photo:
            photo_file_id=(
                message.photo[-1].file_id
            )

        elif message.document:
            document=message.document

            mime_type=str(
                document.mime_type or ""
            ).lower()

            file_name=str(
                document.file_name or ""
            ).lower()

            allowed_document=(
                mime_type.startswith("image/")
                or mime_type=="application/pdf"
                or file_name.endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".heic",
                        ".heif",
                        ".pdf",
                    )
                )
            )

            if allowed_document:
                photo_file_id=document.file_id

        if (
            not text
            and not photo_file_id
        ):
            await message.answer(
                "کد پیگیری یا تصویر رسید "
                "را ارسال کنید."
            )
            return

        db=SessionLocal()

        try:
            from .reseller_bot_order_models import (
                ResellerBotOrder,
            )

            user=linked_user(
                db,
                reseller_id,
                message.from_user.id,
            )

            if not user:
                await state.clear()
                await message.answer(
                    "حساب کاربری پیدا نشد."
                )
                return

            order=(
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.id
                    == order_id,
                    ResellerBotOrder.reseller_id
                    == reseller_id,
                    ResellerBotOrder.customer_user_id
                    == user.id,
                    ResellerBotOrder.telegram_id
                    == message.from_user.id,
                )
                .first()
            )

            if not order:
                await state.clear()
                await message.answer(
                    "سفارش پیدا نشد."
                )
                return

            if order.status != "pending_payment":
                await state.clear()

                await message.answer(
                    "این سفارش قبلاً ثبت شده است."
                )
                return

            order.tracking_code=(
                text[:180]
                if text
                else None
            )

            order.receipt_telegram_file_id=(
                photo_file_id
            )

            order.status="awaiting_review"
            order.submitted_at=datetime.utcnow()
            order.error_text=None

            # TWINPANEL_RECEIPT_DISCOUNT_HOLD_V1
            from .discount_service import (
                hold_discount_for_review,
            )

            hold_discount_for_review(
                db,
                order_kind="reseller_bot",
                order_id=order.id,
            )

            db.commit()

            await state.clear()

            is_renewal = str(
                order.payment_note
                or ""
            ).startswith("renewal:")

            after_approval = (
                "پس از تأیید، همان اشتراک فعلی "
                "تمدید می‌شود و اطلاعات اتصال "
                "بدون تغییر باقی می‌ماند."
                if is_renewal
                else
                "پس از تأیید، اکانت ساخته و "
                "اطلاعات اتصال برای شما ارسال می‌شود."
            )

            await message.answer(
                "✅ <b>پرداخت برای بررسی ثبت شد.</b>\n\n"
                f"شماره سفارش: <b>#{order.id}</b>\n"
                f"مبلغ: "
                f"<b>{int(order.sell_price_toman):,} تومان</b>\n"
                "وضعیت: <b>در انتظار تأیید نماینده</b>\n\n"
                f"{after_approval}",
                reply_markup=_main_keyboard(),
            )

        except Exception:
            db.rollback()
            log.exception(
                "payment proof failed reseller=%s",
                reseller_id,
            )

            await message.answer(
                "ثبت رسید انجام نشد. "
                "دوباره تلاش کنید."
            )

        finally:
            db.close()



    # TWINPANEL_RESELLER_RECEIPT_RECOVERY_V1
    #
    # اگر سرویس بین انتخاب روش پرداخت و ارسال رسید
    # Restart شود، FSM حافظه‌ای از بین می‌رود.
    # این Handler آخرین سفارش پرداخت باز همان کاربر
    # را پیدا می‌کند و رسید را بدون ساخت Order جدید
    # به همان سفارش متصل می‌کند.
    @router.message(
        F.photo | F.document
    )
    async def recover_payment_receipt(
        message: Message,
        state: FSMContext,
    ):
        # TWINPANEL_RESELLER_RECEIPT_RECOVERY_V2
        current_state = await state.get_state()

        log.info(
            "receipt recovery entered reseller=%s telegram=%s state=%s",
            reseller_id,
            message.from_user.id,
            current_state,
        )

        receipt_file_id = None

        if message.photo:
            receipt_file_id = (
                message.photo[-1].file_id
            )

        elif message.document:
            document = message.document

            mime_type = str(
                document.mime_type or ""
            ).lower()

            file_name = str(
                document.file_name or ""
            ).lower()

            allowed = (
                mime_type.startswith("image/")
                or mime_type == "application/pdf"
                or file_name.endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                        ".heic",
                        ".heif",
                        ".pdf",
                    )
                )
            )

            if allowed:
                receipt_file_id = (
                    document.file_id
                )

        if not receipt_file_id:
            return

        db = SessionLocal()

        try:
            from datetime import datetime

            from .reseller_bot_order_models import (
                ResellerBotOrder,
            )

            rows = (
                db.query(ResellerBotOrder)
                .filter(
                    ResellerBotOrder.reseller_id
                    == reseller_id,
                    ResellerBotOrder.telegram_id
                    == message.from_user.id,
                    ResellerBotOrder.status
                    == "pending_payment",
                    ResellerBotOrder.payment_method_id.isnot(
                        None
                    ),
                )
                .order_by(
                    ResellerBotOrder.id.desc()
                )
                .limit(2)
                .all()
            )

            if not rows:
                await message.answer(
                    "سفارش پرداخت در انتظار پیدا نشد."
                )
                return

            if len(rows) > 1:
                await message.answer(
                    "چند سفارش پرداخت باز دارید. "
                    "لطفاً خرید موردنظر را دوباره "
                    "از منوی ربات باز کنید."
                )
                return

            order = rows[0]

            caption = str(
                message.caption or ""
            ).strip()

            order.receipt_telegram_file_id = (
                receipt_file_id
            )

            if caption:
                order.tracking_code = (
                    caption[:180]
                )

            order.status = "awaiting_review"
            order.submitted_at = datetime.utcnow()
            order.error_text = None

            from .discount_service import (
                hold_discount_for_review,
            )

            hold_discount_for_review(
                db,
                order_kind="reseller_bot",
                order_id=order.id,
            )

            db.commit()

            await state.clear()

            await message.answer(
                "✅ <b>رسید ثبت شد.</b>\n\n"
                f"شماره سفارش: "
                f"<b>#{order.id}</b>\n"
                "وضعیت: "
                "<b>در انتظار تأیید نماینده</b>"
            )

        except Exception:
            db.rollback()

            log.exception(
                "receipt recovery failed reseller=%s",
                reseller_id,
            )

            await message.answer(
                "ثبت رسید انجام نشد. "
                "دوباره تلاش کنید."
            )

        finally:
            db.close()


    return router



# TWINPANEL_HIDE_MAIN_RENEW_BUTTON_V1
# Renewal remains available from each subscription detail page.
_twinpanel_original_main_keyboard = _main_keyboard


def _main_keyboard(*args, **kwargs):
    markup = _twinpanel_original_main_keyboard(
        *args,
        **kwargs,
    )

    rows = []

    for row in list(
        getattr(markup, "keyboard", None)
        or []
    ):
        filtered = [
            button
            for button in row
            if str(
                getattr(
                    button,
                    "text",
                    "",
                )
            ).strip()
            != "🔄 تمدید اشتراک"
        ]

        if filtered:
            rows.append(filtered)

    if hasattr(markup, "model_copy"):
        return markup.model_copy(
            update={
                "keyboard": rows,
            }
        )

    markup.keyboard = rows
    return markup


async def _run_bot(
    reseller_id: int,
    token: str,
):
    bot = Bot(
        token=token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        ),
    )

    dp = Dispatcher(
        storage=MemoryStorage()
    )

    dp.include_router(
        build_router(
            reseller_id
        )
    )

    try:
        me = await bot.get_me()

        log.info(
            "starting reseller=%s bot=@%s",
            reseller_id,
            me.username,
        )

        await bot.delete_webhook(
            drop_pending_updates=False
        )

        await dp.start_polling(
            bot,
            handle_signals=False,
            allowed_updates=(
                dp.resolve_used_update_types()
            ),
        )

    finally:
        await bot.session.close()


async def supervisor():
    running = {}

    while True:
        db = SessionLocal()

        try:
            rows = (
                db.query(
                    ResellerBotSettings
                )
                .join(
                    Reseller,
                    Reseller.id
                    == ResellerBotSettings.reseller_id,
                )
                .filter(
                    ResellerBotSettings.is_active.is_(
                        True
                    ),
                    ResellerBotSettings.bot_token_encrypted.isnot(
                        None
                    ),
                    Reseller.is_active.is_(
                        True
                    ),
                )
                .all()
            )

            desired = {}
            token_owners = {}

            for row in rows:
                try:
                    token = decrypt_bot_token(
                        row.bot_token_encrypted
                    )

                    digest = hashlib.sha256(
                        token.encode()
                    ).hexdigest()

                    # Prevent the same BotFather token
                    # from running for two resellers.
                    if digest in token_owners:
                        log.error(
                            "duplicate bot token: "
                            "reseller=%s already owned by=%s",
                            row.reseller_id,
                            token_owners[digest],
                        )
                        continue

                    token_owners[digest] = (
                        row.reseller_id
                    )

                    desired[
                        int(row.reseller_id)
                    ] = (
                        token,
                        digest,
                    )

                except Exception:
                    log.exception(
                        "cannot decrypt reseller=%s",
                        row.reseller_id,
                    )

        finally:
            db.close()

        # Stop disabled/removed bots.
        for reseller_id in list(
            running
        ):
            item = running[
                reseller_id
            ]

            task = item["task"]

            wanted = desired.get(
                reseller_id
            )

            changed = bool(
                wanted
                and wanted[1]
                != item["digest"]
            )

            if (
                not wanted
                or changed
            ):
                log.info(
                    "stopping reseller=%s",
                    reseller_id,
                )

                task.cancel()

                try:
                    await task
                except BaseException:
                    pass

                running.pop(
                    reseller_id,
                    None,
                )

        # Restart crashed tasks.
        for reseller_id in list(
            running
        ):
            if running[
                reseller_id
            ]["task"].done():
                try:
                    running[
                        reseller_id
                    ]["task"].result()
                except BaseException:
                    log.exception(
                        "bot crashed reseller=%s",
                        reseller_id,
                    )

                running.pop(
                    reseller_id,
                    None,
                )

        # Start newly activated bots.
        for reseller_id, (
            token,
            digest,
        ) in desired.items():

            if reseller_id in running:
                continue

            task = asyncio.create_task(
                _run_bot(
                    reseller_id,
                    token,
                )
            )

            running[
                reseller_id
            ] = {
                "task": task,
                "digest": digest,
            }

        await asyncio.sleep(
            POLL_INTERVAL
        )


def main():
    asyncio.run(
        supervisor()
    )


if __name__ == "__main__":
    main()
