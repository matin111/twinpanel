from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..routers.auth import get_current_user
from ..storefront_settings_models import StorefrontSettings


router = APIRouter(
    prefix="/v1/storefront/settings",
    tags=["storefront-settings"],
)


DEFAULTS: dict[str, Any] = {
    # Template selection is intentionally persisted as an id inside the existing
    # JSON settings row. Installed template code ships with product updates, so
    # adding a future template never requires a database migration.
    "active_template": "conversion-2027",

    # Hero - Persian + English
    "hero_kicker": "۵ پروتکل، یک حساب کاربری",
    "hero_kicker_en": "5 protocols, one account",
    "hero_title": "اشتراک VPN برای چند روش اتصال،",
    "hero_title_en": "VPN plans for multiple connection methods,",
    "hero_highlight": "از یک پنل.",
    "hero_highlight_en": "from one panel.",
    "hero_description": "پلن را بر اساس نیاز انتخاب کنید؛ حجم، مدت، تعداد دستگاه و اطلاعات اتصال بعد از خرید در پنل کاربری در دسترس قرار می‌گیرد.",
    "hero_description_en": "Choose a plan for your needs. Traffic, duration, device limits and connection details are available in your customer panel after purchase.",
    "hero_primary_button": "مشاهده پلن‌ها",
    "hero_primary_button_en": "View plans",
    "hero_secondary_button": "ورود به پنل کاربری",
    "hero_secondary_button_en": "Customer panel",

    # Plans
    "plans_tag": "اشتراک‌های VPN",
    "plans_tag_en": "VPN PLANS",
    "plans_title": "انتخاب اشتراک",
    "plans_title_en": "Choose your plan",
    "plans_description": "حجم، مدت، تعداد دستگاه و پروتکل‌های هر پلن قبل از خرید نمایش داده می‌شود.",
    "plans_description_en": "Compare traffic, duration, device limits and protocols before purchase.",

    # Protocols
    "protocols_tag": "پروتکل‌های اتصال",
    "protocols_tag_en": "PROTOCOLS",
    "protocols_title": "روش اتصال مناسب خودت را انتخاب کن.",
    "protocols_title_en": "Choose the connection method that fits you.",
    "protocols_description": "هر اشتراک می‌تواند چند پروتکل داشته باشد. روی هر گزینه بزن تا کاربرد و ویژگی‌های آن را ببینی.",
    "protocols_description_en": "A subscription can include multiple protocols. Review each option to find the best fit.",

    # Services
    "services_tag": "خدمات TwinPanel",
    "services_tag_en": "SERVICES",
    "services_title": "بعد از خرید، همه‌چیز داخل حساب شماست.",
    "services_title_en": "Everything stays inside your account after purchase.",
    "services_description": "اطلاعات اتصال، حجم و اعتبار و اشتراک‌های شما از پنل کاربری در دسترس است.",
    "services_description_en": "Connection details, traffic, wallet balance and subscriptions are available from the customer panel.",

    # Guides
    "guides_tag": "آموزش اتصال",
    "guides_tag_en": "SETUP GUIDES",
    "guides_title": "راهنمای نصب و اتصال برای همه دستگاه‌ها",
    "guides_title_en": "Setup guidance for every device",
    "guides_description": "پروتکل و سیستم‌عامل را انتخاب کنید تا مراحل نصب و اتصال نمایش داده شود.",
    "guides_description_en": "Choose a protocol and operating system to see the connection flow.",

    # Customer panel
    "account_tag": "پنل کاربری TwinPanel",
    "account_tag_en": "CUSTOMER PANEL",
    "account_title": "خرید و مدیریت اشتراک، در یک حساب.",
    "account_title_en": "Purchase and manage subscriptions in one account.",
    "account_description": "بعد از ورود می‌توانید اشتراک، حجم، اعتبار و اطلاعات اتصال خود را مدیریت کنید.",
    "account_description_en": "Sign in to manage subscriptions, traffic, wallet balance and connection details.",

    # FAQ
    "faq_tag": "سوالات متداول",
    "faq_tag_en": "FAQ",
    "faq_title": "سوالات متداول",
    "faq_title_en": "Frequently asked questions",
    "faq_description": "پاسخ سوالات متداول درباره خرید، حجم، دستگاه و اتصال.",
    "faq_description_en": "Answers to common questions about purchases, traffic, devices and connectivity.",

    # Visibility
    "show_plans": True,
    "show_protocols": True,
    "show_services": True,
    "show_guides": True,
    "show_account": True,
    "show_faq": True,

    # Ordering
    "section_order": [
        "plans",
        "protocols",
        "services",
        "guides",
        "account",
        "faq",
    ],

    # SEO
    "seo_title": "TwinPanel | اشتراک VPN",
    "seo_description": "خرید و مدیریت اشتراک VPN با پشتیبانی از چند روش اتصال و پنل کاربری.",
    "seo_keywords": "VPN, خرید VPN, OpenVPN, WireGuard, Cisco, L2TP, V2Ray",
    "canonical_url": "https://movilineapp.com/",
    "og_title": "TwinPanel | اشتراک VPN",
    "og_description": "خرید و مدیریت اشتراک VPN از یک پنل.",
    "og_image": "",
    "robots_index": True,
    "robots_follow": True,
}


BOOL_FIELDS = {
    "show_plans",
    "show_protocols",
    "show_services",
    "show_guides",
    "show_account",
    "show_faq",
    "robots_index",
    "robots_follow",
}

ORDER_KEYS = {
    "plans",
    "protocols",
    "services",
    "guides",
    "account",
    "faq",
}


def _clean_text(value: Any, fallback: str, max_length: int = 2500) -> str:
    if value is None:
        return fallback
    result = str(value).strip()
    if not result:
        return fallback
    return result[:max_length]


def _normalize(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    result = dict(DEFAULTS)

    for key, default in DEFAULTS.items():
        if key == "section_order":
            continue
        if key in BOOL_FIELDS:
            if key in source:
                result[key] = bool(source[key])
            continue
        if key in source:
            max_length = 120 if key == "active_template" else 2500
            result[key] = _clean_text(source[key], str(default), max_length=max_length)

    order = source.get("section_order", DEFAULTS["section_order"])
    normalized_order: list[str] = []
    if isinstance(order, list):
        for item in order:
            key = str(item)
            if key in ORDER_KEYS and key not in normalized_order:
                normalized_order.append(key)

    for key in DEFAULTS["section_order"]:
        if key not in normalized_order:
            normalized_order.append(key)

    result["section_order"] = normalized_order
    return result


def _row(db: Session) -> StorefrontSettings:
    item = (
        db.query(StorefrontSettings)
        .order_by(StorefrontSettings.id)
        .first()
    )
    if item:
        return item

    item = StorefrontSettings(id=1, content=dict(DEFAULTS))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _response(item: StorefrontSettings) -> dict[str, Any]:
    result = _normalize(item.content)
    result["updated_at"] = item.updated_at.isoformat() if item.updated_at else None
    return result


@router.get("")
def public_storefront_settings(db: Session = Depends(get_db)):
    return _response(_row(db))


@router.put("")
def update_storefront_settings(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin_only")

    item = _row(db)
    current = _normalize(item.content)
    item.content = _normalize({**current, **payload})
    db.add(item)
    db.commit()
    db.refresh(item)
    return _response(item)
