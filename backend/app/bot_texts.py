from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from .models_reseller import Reseller, ResellerBotSettings
from .runtime_settings_model import RuntimeSetting


@dataclass(frozen=True)
class BotTextSpec:
    key: str
    label_fa: str
    label_en: str
    help_fa: str
    help_en: str
    max_length: int = 1200


BOT_TEXT_SPECS: tuple[BotTextSpec, ...] = (
    BotTextSpec(
        key="welcome",
        label_fa="پیام خوش‌آمدگویی",
        label_en="Welcome message",
        help_fa="متن شروع ربات. نام کاربر یا برند که توسط ربات ساخته می‌شود دست‌نخورده می‌ماند.",
        help_en="Bot start copy. Dynamic customer/brand values remain managed by the bot.",
        max_length=2500,
    ),
    BotTextSpec(
        key="plan_select",
        label_fa="انتخاب پلن",
        label_en="Plan selection",
        help_fa="متنی که قبل از فهرست پلن‌ها نمایش داده می‌شود.",
        help_en="Prompt shown before the available plan list.",
    ),
    BotTextSpec(
        key="payment_select",
        label_fa="انتخاب روش پرداخت",
        label_en="Payment selection",
        help_fa="متن راهنما هنگام انتخاب روش پرداخت.",
        help_en="Prompt shown while choosing a payment method.",
    ),
    BotTextSpec(
        key="receipt_request",
        label_fa="درخواست ارسال رسید",
        label_en="Receipt request",
        help_fa="فقط متن راهنما تغییر می‌کند؛ ثبت رسید و اطلاعات پرداخت همان منطق فعلی را دارد.",
        help_en="Only the copy changes; receipt/payment behavior stays unchanged.",
    ),
    BotTextSpec(
        key="awaiting_approval",
        label_fa="در انتظار تأیید",
        label_en="Awaiting approval",
        help_fa="عبارت وضعیت پس از ثبت پرداخت یا رسید.",
        help_en="Status wording shown after payment or receipt submission.",
    ),
    BotTextSpec(
        key="purchase_success",
        label_fa="خرید / پرداخت موفق",
        label_en="Purchase success",
        help_fa="عنوان پیام موفقیت؛ مبلغ، نام کاربری، لینک و سایر اطلاعات خودکار باقی می‌مانند.",
        help_en="Success title; dynamic amount/account/link data remain automatic.",
    ),
    BotTextSpec(
        key="payment_rejected",
        label_fa="رد پرداخت",
        label_en="Payment rejected",
        help_fa="عنوان پیام رد پرداخت. دلیل رد همچنان از رکورد واقعی پرداخت می‌آید.",
        help_en="Rejected-payment title. The real rejection reason remains automatic.",
    ),
    BotTextSpec(
        key="renewal_intro",
        label_fa="تمدید اشتراک",
        label_en="Renewal",
        help_fa="عنوان ثابت بخش تمدید؛ مشخصات پلن و مبلغ خودکار باقی می‌مانند.",
        help_en="Renewal section title; plan and amount data remain automatic.",
    ),
    BotTextSpec(
        key="support_intro",
        label_fa="پشتیبانی",
        label_en="Support",
        help_fa="عنوان ثابت پیام پشتیبانی.",
        help_en="Static support message title.",
    ),
)

_SPEC_BY_KEY = {item.key: item for item in BOT_TEXT_SPECS}


ADMIN_DEFAULTS = {
    "welcome": (
        "مدیریت و خرید اشتراک VPN از داخل تلگرام.\n\n"
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
    ),
    "plan_select": "پلن موردنظر را انتخاب کنید:",
    "payment_select": "روش پرداخت را انتخاب کنید:",
    "receipt_request": "رسید پرداخت را ارسال کنید.",
    "awaiting_approval": "در انتظار بررسی",
    "purchase_success": "پرداخت شما تأیید شد",
    "payment_rejected": "پرداخت تأیید نشد",
    "renewal_intro": "تمدید اشتراک",
    "support_intro": "پشتیبانی",
}


RESELLER_DEFAULTS = {
    "welcome": "👋 خوش آمدید.",
    "plan_select": "پلن موردنظر را انتخاب کنید:",
    "payment_select": "روش پرداخت را انتخاب کنید:",
    "receipt_request": "کد پیگیری یا تصویر رسید را همین‌جا ارسال کنید.",
    "awaiting_approval": "در انتظار تأیید نماینده",
    "purchase_success": "خرید با موفقیت انجام شد.",
    "payment_rejected": "پرداخت تأیید نشد",
    "renewal_intro": "تمدید اشتراک",
    "support_intro": "پشتیبانی",
}


def _setting_key(scope: str, key: str, reseller_id: int | None = None) -> str:
    if scope == "admin":
        return f"telegram.bot_text.admin.{key}"

    if scope == "reseller" and reseller_id:
        return f"telegram.bot_text.reseller.{int(reseller_id)}.{key}"

    raise ValueError("invalid bot text scope")


def _setting_value(db: Session, setting_key: str) -> str | None:
    row = db.get(RuntimeSetting, setting_key)
    if not row:
        return None

    value = str(row.setting_value or "").strip()
    return value or None


def _put_setting(db: Session, setting_key: str, value: str | None) -> None:
    normalized = str(value or "").strip()
    row = db.get(RuntimeSetting, setting_key)

    if not normalized:
        if row:
            db.delete(row)
        return

    if row:
        row.setting_value = normalized
        row.updated_at = datetime.utcnow()
        return

    db.add(
        RuntimeSetting(
            setting_key=setting_key,
            setting_value=normalized,
            updated_at=datetime.utcnow(),
        )
    )


def _reseller_bot_row(db: Session, reseller_id: int, *, create: bool = False) -> ResellerBotSettings | None:
    row = (
        db.query(ResellerBotSettings)
        .filter(ResellerBotSettings.reseller_id == int(reseller_id))
        .first()
    )

    if row or not create:
        return row

    row = ResellerBotSettings(
        reseller_id=int(reseller_id),
        is_active=False,
    )
    db.add(row)
    db.flush()
    return row


def _reseller_brand(reseller: Reseller | None) -> str:
    if not reseller:
        return "فروشگاه"
    return str(reseller.brand_name or reseller.name or "فروشگاه").strip()


def _default_text(scope: str, key: str, reseller: Reseller | None = None) -> str:
    if scope == "admin":
        return ADMIN_DEFAULTS[key]

    if scope == "reseller":
        if key == "welcome":
            return f"👋 به <b>{_reseller_brand(reseller)}</b> خوش آمدید."
        return RESELLER_DEFAULTS[key]

    raise ValueError("invalid bot text scope")


def _custom_text(
    db: Session,
    scope: str,
    key: str,
    reseller_id: int | None = None,
) -> str | None:
    if scope == "reseller" and key == "welcome" and reseller_id:
        row = _reseller_bot_row(db, int(reseller_id))
        value = str(row.welcome_message or "").strip() if row else ""
        return value or None

    return _setting_value(
        db,
        _setting_key(scope, key, reseller_id),
    )


def bot_text_catalog(
    db: Session,
    *,
    scope: str,
    reseller: Reseller | None = None,
) -> dict:
    reseller_id = int(reseller.id) if reseller else None
    items = []

    for spec in BOT_TEXT_SPECS:
        custom = _custom_text(
            db,
            scope,
            spec.key,
            reseller_id,
        )
        default = _default_text(scope, spec.key, reseller)
        items.append(
            {
                "key": spec.key,
                "label_fa": spec.label_fa,
                "label_en": spec.label_en,
                "help_fa": spec.help_fa,
                "help_en": spec.help_en,
                "max_length": spec.max_length,
                "default_text": default,
                "custom_text": custom,
                "effective_text": custom or default,
                "is_custom": bool(custom),
            }
        )

    return {
        "scope": scope,
        "reseller_id": reseller_id,
        "items": items,
    }


def save_bot_texts(
    db: Session,
    *,
    scope: str,
    values: dict[str, str | None],
    reseller: Reseller | None = None,
) -> dict:
    reseller_id = int(reseller.id) if reseller else None

    unknown = sorted(set(values) - set(_SPEC_BY_KEY))
    if unknown:
        raise ValueError("unknown bot text keys: " + ", ".join(unknown))

    for key, value in values.items():
        spec = _SPEC_BY_KEY[key]
        normalized = str(value or "").strip()

        if len(normalized) > spec.max_length:
            raise ValueError(f"{key} exceeds {spec.max_length} characters")

        if scope == "reseller" and key == "welcome":
            if not reseller_id:
                raise ValueError("reseller is required")
            row = _reseller_bot_row(db, reseller_id, create=True)
            row.welcome_message = normalized or None
            row.updated_at = datetime.utcnow()
            continue

        _put_setting(
            db,
            _setting_key(scope, key, reseller_id),
            normalized or None,
        )

    db.commit()
    return bot_text_catalog(db, scope=scope, reseller=reseller)


def reset_bot_texts(
    db: Session,
    *,
    scope: str,
    keys: list[str] | None = None,
    reseller: Reseller | None = None,
) -> dict:
    selected = list(_SPEC_BY_KEY) if keys is None else list(dict.fromkeys(keys))
    unknown = sorted(set(selected) - set(_SPEC_BY_KEY))
    if unknown:
        raise ValueError("unknown bot text keys: " + ", ".join(unknown))

    reseller_id = int(reseller.id) if reseller else None

    for key in selected:
        if scope == "reseller" and key == "welcome":
            if reseller_id:
                row = _reseller_bot_row(db, reseller_id)
                if row:
                    row.welcome_message = None
                    row.updated_at = datetime.utcnow()
            continue

        _put_setting(
            db,
            _setting_key(scope, key, reseller_id),
            None,
        )

    db.commit()
    return bot_text_catalog(db, scope=scope, reseller=reseller)


def custom_bot_texts(
    db: Session,
    *,
    scope: str,
    reseller_id: int | None = None,
) -> dict[str, str]:
    result: dict[str, str] = {}

    for spec in BOT_TEXT_SPECS:
        value = _custom_text(
            db,
            scope,
            spec.key,
            reseller_id,
        )
        if value:
            result[spec.key] = value

    return result
