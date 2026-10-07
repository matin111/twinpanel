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

    # ---------------------------------------------------------
    # Hero
    # ---------------------------------------------------------

    "hero_kicker":
        "۵ پروتکل، یک حساب کاربری",

    "hero_title":
        "اشتراک VPN برای چند روش اتصال،",

    "hero_highlight":
        "از یک پنل.",

    "hero_description":
        "پلن را بر اساس نیاز انتخاب کنید؛ حجم، مدت، تعداد دستگاه و اطلاعات اتصال بعد از خرید در پنل کاربری در دسترس قرار می‌گیرد.",

    "hero_primary_button":
        "مشاهده پلن‌ها",

    "hero_secondary_button":
        "ورود به پنل کاربری",


    # ---------------------------------------------------------
    # Plans
    # ---------------------------------------------------------

    "plans_tag":
        "اشتراک‌های VPN",

    "plans_title":
        "انتخاب اشتراک",

    "plans_description":
        "حجم، مدت، تعداد دستگاه و پروتکل‌های هر پلن قبل از خرید نمایش داده می‌شود.",


    # ---------------------------------------------------------
    # Protocols
    # ---------------------------------------------------------

    "protocols_tag":
        "پروتکل‌های اتصال",

    "protocols_title":
        "روش اتصال مناسب خودت را انتخاب کن.",

    "protocols_description":
        "هر اشتراک می‌تواند چند پروتکل داشته باشد. روی هر گزینه بزن تا کاربرد و ویژگی‌های آن را ببینی.",


    # ---------------------------------------------------------
    # Services
    # ---------------------------------------------------------

    "services_tag":
        "خدمات TwinPanel",

    "services_title":
        "بعد از خرید، همه‌چیز داخل حساب شماست.",

    "services_description":
        "اطلاعات اتصال، حجم و اعتبار و اشتراک‌های شما از پنل کاربری در دسترس است.",


    # ---------------------------------------------------------
    # Guides
    # ---------------------------------------------------------

    "guides_tag":
        "آموزش اتصال",

    "guides_title":
        "راهنمای نصب و اتصال برای همه دستگاه‌ها",

    "guides_description":
        "پروتکل و سیستم‌عامل را انتخاب کنید تا مراحل نصب و اتصال نمایش داده شود.",


    # ---------------------------------------------------------
    # Customer panel
    # ---------------------------------------------------------

    "account_tag":
        "پنل کاربری TwinPanel",

    "account_title":
        "خرید و مدیریت اشتراک، در یک حساب.",

    "account_description":
        "بعد از ورود می‌توانید اشتراک، حجم، اعتبار و اطلاعات اتصال خود را مدیریت کنید.",


    # ---------------------------------------------------------
    # FAQ
    # ---------------------------------------------------------

    "faq_tag":
        "سوالات متداول",

    "faq_title":
        "سوالات متداول",

    "faq_description":
        "پاسخ سوالات متداول درباره خرید، حجم، دستگاه و اتصال.",


    # ---------------------------------------------------------
    # Visibility
    # ---------------------------------------------------------

    "show_plans": True,
    "show_protocols": True,
    "show_services": True,
    "show_guides": True,
    "show_account": True,
    "show_faq": True,


    # ---------------------------------------------------------
    # Ordering
    # ---------------------------------------------------------

    "section_order": [
        "plans",
        "protocols",
        "services",
        "guides",
        "account",
        "faq",
    ],


    # ---------------------------------------------------------
    # SEO
    # ---------------------------------------------------------

    "seo_title":
        "TwinPanel | اشتراک VPN",

    "seo_description":
        "خرید و مدیریت اشتراک VPN با پشتیبانی از چند روش اتصال و پنل کاربری.",

    "seo_keywords":
        "VPN, خرید VPN, OpenVPN, WireGuard, Cisco, L2TP, V2Ray",

    "canonical_url":
        "https://movilineapp.com/",

    "og_title":
        "TwinPanel | اشتراک VPN",

    "og_description":
        "خرید و مدیریت اشتراک VPN از یک پنل.",

    "og_image":
        "",

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


def _clean_text(
    value: Any,
    fallback: str,
    max_length: int = 2500,
) -> str:

    if value is None:
        return fallback

    result = str(value).strip()

    if not result:
        return fallback

    return result[:max_length]


def _normalize(
    raw: Any,
) -> dict[str, Any]:

    source = (
        raw
        if isinstance(raw, dict)
        else {}
    )

    result = dict(DEFAULTS)

    for key, default in DEFAULTS.items():

        if key == "section_order":
            continue

        if key in BOOL_FIELDS:
            if key in source:
                result[key] = bool(
                    source[key]
                )
            continue

        if key in source:
            result[key] = _clean_text(
                source[key],
                str(default),
            )


    order = source.get(
        "section_order",
        DEFAULTS["section_order"],
    )

    normalized_order: list[str] = []

    if isinstance(order, list):

        for item in order:

            key = str(item)

            if (
                key in ORDER_KEYS
                and key not in normalized_order
            ):
                normalized_order.append(key)


    for key in DEFAULTS["section_order"]:

        if key not in normalized_order:
            normalized_order.append(key)


    result["section_order"] = normalized_order

    return result


def _row(
    db: Session,
) -> StorefrontSettings:

    item = (
        db.query(StorefrontSettings)
        .order_by(StorefrontSettings.id)
        .first()
    )

    if item:
        return item

    item = StorefrontSettings(
        id=1,
        content=dict(DEFAULTS),
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item


def _response(
    item: StorefrontSettings,
) -> dict[str, Any]:

    result = _normalize(
        item.content
    )

    result["updated_at"] = (
        item.updated_at.isoformat()
        if item.updated_at
        else None
    )

    return result


@router.get("")
def public_storefront_settings(
    db: Session = Depends(get_db),
):

    item = _row(db)

    return _response(item)


@router.put("")
def update_storefront_settings(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="admin_only",
        )

    item = _row(db)

    current = _normalize(
        item.content
    )

    merged = {
        **current,
        **payload,
    }

    item.content = _normalize(
        merged
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return _response(item)
