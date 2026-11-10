"""Versioned, validation-first appearance preferences shared by all TwinConnect clients."""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .branding_models import BrandingSettings
from .central_app_appearance_models import CentralAppAppearance
from .central_app_models import CentralAppContact

COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
DEFAULTS = {
    "primary_color": "#7C3AED",
    "secondary_color": "#4F46E5",
    "button_color": "#7C3AED",
    "background_color": "#101018",
    "surface_color": "#20202A",
    "background_style": "gradient",
    "background_image_url": None,
    "theme_mode": "dark",
}


class AppearanceIn(BaseModel):
    primary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    button_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    background_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    surface_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    background_style: str = Field(pattern=r"^(solid|gradient|image)$")
    background_image_url: str | None = Field(default=None, max_length=500)
    theme_mode: str = Field(pattern=r"^(light|dark|system)$")


def _validate_background_url(value: str | None) -> str | None:
    if not value:
        return None
    url = urlsplit(value.strip())
    try:
        invalid = (url.scheme != "https" or not url.hostname or url.username or
                   url.password or url.query or url.fragment or url.port not in (None, 443))
    except ValueError:
        invalid = True
    if invalid:
        raise HTTPException(status_code=422, detail="INVALID_BACKGROUND_IMAGE_URL")
    host = url.hostname.lower()
    if host.endswith(".") or host in ("localhost", "local") or not host.count("."):
        raise HTTPException(status_code=422, detail="INVALID_BACKGROUND_IMAGE_URL")
    try:
        ipaddress.ip_address(host)
        raise HTTPException(status_code=422, detail="BACKGROUND_HOST_MUST_BE_DNS")
    except ValueError:
        pass
    if (len(host) > 253 or any(not LABEL.fullmatch(label) for label in host.split(".")) or
            host.endswith((".local", ".internal", ".localhost", ".invalid", ".test", ".example"))):
        raise HTTPException(status_code=422, detail="INVALID_BACKGROUND_IMAGE_URL")
    # No data:, javascript:, local file://, URL fragment, embedded credentials
    # or redirects controlled by us. The client decides whether to fetch.
    return url.geturl()


def validate_appearance(payload: AppearanceIn) -> dict:
    values = payload.model_dump()
    for key in ("primary_color", "secondary_color", "button_color", "background_color", "surface_color"):
        color = values[key]
        if not COLOR.fullmatch(color):
            raise HTTPException(status_code=422, detail=f"{key}_invalid")
        values[key] = color.upper()
    values["background_image_url"] = _validate_background_url(values["background_image_url"])
    if values["background_style"] == "image" and not values["background_image_url"]:
        raise HTTPException(status_code=422, detail="BACKGROUND_IMAGE_REQUIRED")
    return values


def resolve_appearance(db: Session, reseller_id: int) -> dict:
    """No other reseller's row is ever inherited or returned."""
    row = db.get(CentralAppAppearance, int(reseller_id))
    if row:
        return {key: getattr(row, key) for key in DEFAULTS}
    values = dict(DEFAULTS)
    contact = db.get(CentralAppContact, int(reseller_id))
    if contact:
        for key in ("primary_color", "secondary_color"):
            color = getattr(contact, key)
            if color and COLOR.fullmatch(color):
                values[key] = color.upper()
    if not reseller_id:
        branding = db.query(BrandingSettings).first()
        if branding:
            for key in ("primary_color", "secondary_color"):
                color = getattr(branding, key, None)
                if color and COLOR.fullmatch(color) and not (contact and getattr(contact, key, None)):
                    values[key] = color.upper()
    values["button_color"] = values["primary_color"]
    return values


def save_appearance(db: Session, reseller_id: int, payload: AppearanceIn) -> dict:
    values = validate_appearance(payload)
    row = db.get(CentralAppAppearance, int(reseller_id))
    if row is None:
        row = CentralAppAppearance(reseller_id=int(reseller_id), **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    db.commit()
    return resolve_appearance(db, reseller_id)


def reset_appearance(db: Session, reseller_id: int) -> dict:
    row = db.get(CentralAppAppearance, int(reseller_id))
    if row:
        db.delete(row)
        db.commit()
    return resolve_appearance(db, reseller_id)
