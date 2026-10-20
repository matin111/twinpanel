from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..routers.auth import get_current_user
from ..storefront_defaults import DEFAULTS
from ..storefront_settings_models import StorefrontSettings


router = APIRouter(
    prefix="/v1/storefront/settings",
    tags=["storefront-settings"],
)


BOOL_FIELDS = {
    "show_plans",
    "show_protocols",
    "show_services",
    "show_guides",
    "show_account",
    "show_faq",
    "show_final_cta",
    "show_contact",
    "show_telegram",
    "show_instagram",
    "show_whatsapp",
    "robots_index",
    "robots_follow",
}

URL_FIELDS = {
    "telegram_url",
    "instagram_url",
    "whatsapp_url",
    "canonical_url",
    "og_image",
}

ORDER_KEYS = {
    "plans",
    "protocols",
    "services",
    "guides",
    "account",
    "faq",
}

TEMPLATE_OPTIONS_KEY = "_template_options"
TEMPLATE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}$")
OPTION_KEY_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}$")
MAX_TEMPLATE_COUNT = 32
MAX_TEMPLATE_FIELDS = 256
MAX_TEMPLATE_DEPTH = 5
MAX_TEMPLATE_STRING = 5000
MAX_TEMPLATE_LIST = 96
_DROP = object()


def _clean_text(value: Any, fallback: str, max_length: int = 2500) -> str:
    if value is None:
        return fallback
    result = str(value).strip()
    if not result:
        return fallback
    return result[:max_length]


def _clean_url(value: Any, fallback: str) -> str:
    result = _clean_text(value, fallback, max_length=1000)
    if not result:
        return fallback
    parsed = urlparse(result)
    if parsed.scheme not in {"http", "https"}:
        return fallback
    return result


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
            if key in URL_FIELDS:
                result[key] = _clean_url(source[key], str(default))
                continue
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


def _clean_template_value(value: Any, depth: int = 0) -> Any:
    if depth > MAX_TEMPLATE_DEPTH:
        return _DROP
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else _DROP
    if isinstance(value, str):
        return value[:MAX_TEMPLATE_STRING]
    if isinstance(value, list):
        result: list[Any] = []
        for item in value[:MAX_TEMPLATE_LIST]:
            cleaned = _clean_template_value(item, depth + 1)
            if cleaned is not _DROP:
                result.append(cleaned)
        return result
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, raw_value in list(value.items())[:MAX_TEMPLATE_FIELDS]:
            key = str(raw_key)
            if not OPTION_KEY_RE.fullmatch(key):
                continue
            cleaned = _clean_template_value(raw_value, depth + 1)
            if cleaned is not _DROP:
                result[key] = cleaned
        return result
    return _DROP


def _clean_template_id(value: Any) -> str:
    template_id = str(value or "").strip()
    if not TEMPLATE_ID_RE.fullmatch(template_id):
        raise HTTPException(status_code=422, detail="invalid_template_id")
    return template_id


def _clean_template_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="template_settings_must_be_object")
    cleaned = _clean_template_value(raw)
    return cleaned if isinstance(cleaned, dict) else {}


def _normalize_template_options(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for raw_template_id, raw_payload in list(raw.items())[:MAX_TEMPLATE_COUNT]:
        template_id = str(raw_template_id or "").strip()
        if not TEMPLATE_ID_RE.fullmatch(template_id) or not isinstance(raw_payload, dict):
            continue
        cleaned = _clean_template_value(raw_payload)
        if isinstance(cleaned, dict):
            result[template_id] = cleaned
    return result


def _stored_template_options(item: StorefrontSettings) -> dict[str, dict[str, Any]]:
    source = item.content if isinstance(item.content, dict) else {}
    return _normalize_template_options(source.get(TEMPLATE_OPTIONS_KEY))


def _content_with_template_options(
    base: dict[str, Any],
    template_options: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {**base, TEMPLATE_OPTIONS_KEY: template_options}


def _row(db: Session) -> StorefrontSettings:
    item = (
        db.query(StorefrontSettings)
        .order_by(StorefrontSettings.id)
        .first()
    )
    if item:
        return item

    item = StorefrontSettings(
        id=1,
        content=_content_with_template_options(dict(DEFAULTS), {}),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _response(item: StorefrontSettings) -> dict[str, Any]:
    result = _normalize(item.content)
    result["updated_at"] = item.updated_at.isoformat() if item.updated_at else None
    return result


def _template_response(item: StorefrontSettings) -> dict[str, Any]:
    return {
        "templates": _stored_template_options(item),
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("")
def public_storefront_settings(db: Session = Depends(get_db)):
    return _response(_row(db))


@router.get("/templates")
def public_storefront_template_settings(db: Session = Depends(get_db)):
    return _template_response(_row(db))


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
    template_options = _stored_template_options(item)
    item.content = _content_with_template_options(
        _normalize({**current, **payload}),
        template_options,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _response(item)


@router.put("/templates/{template_id}")
def update_storefront_template_settings(
    template_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin_only")

    clean_id = _clean_template_id(template_id)
    item = _row(db)
    template_options = _stored_template_options(item)
    template_options[clean_id] = _clean_template_payload(payload)
    item.content = _content_with_template_options(
        _normalize(item.content),
        template_options,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "template_id": clean_id,
        "settings": template_options[clean_id],
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.delete("/templates/{template_id}")
def reset_storefront_template_settings(
    template_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin_only")

    clean_id = _clean_template_id(template_id)
    item = _row(db)
    template_options = _stored_template_options(item)
    template_options.pop(clean_id, None)
    item.content = _content_with_template_options(
        _normalize(item.content),
        template_options,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "template_id": clean_id,
        "settings": {},
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
