"""Read-only client brand discovery and authenticated owner/reseller settings.

This router never provisions VPNs, changes subscriptions, or exposes the
vendor license key to a client. The existing public share token is a bearer
credential, matching the current /v1/connect contract.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..branding_models import BrandingSettings
from ..central_app_identity import (
    central_app_entitled, installation_namespace, reseller_prefix,
)
from ..central_app_models import CentralAppContact
from ..database import get_db
from ..deps import require_admin, require_reseller
from ..models_reseller import Reseller, ResellerSubscription
from ..system_release import (
    _vendor_post, ensure_installation_id, load_license_state,
)
from .account_delivery import _subscription_from_share_token

router = APIRouter(prefix="/v1/central-app", tags=["central-app"])
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ContactIn(BaseModel):
    logo_url: str | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=16)
    secondary_color: str | None = Field(default=None, max_length=16)
    telegram_url: str | None = Field(default=None, max_length=500)
    renewal_url: str | None = Field(default=None, max_length=500)
    support_phone: str | None = Field(default=None, max_length=32)
    website_url: str | None = Field(default=None, max_length=500)


class RegisterIn(BaseModel):
    api_origin: str = Field(min_length=12, max_length=500)


def _url(raw: str | None, *, relative_allowed: bool = False) -> str | None:
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    if relative_allowed and value.startswith("/") and not value.startswith("//"):
        if "\\" not in value and "?" not in value and "#" not in value:
            return value
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password):
        raise HTTPException(status_code=422, detail="https_url_required")
    return value


def _clean_contact(payload: ContactIn) -> dict:
    values = payload.model_dump()
    for key in ("logo_url", "telegram_url", "renewal_url", "website_url"):
        values[key] = _url(
            values[key], relative_allowed=(key == "logo_url")
        )
    for key in ("primary_color", "secondary_color"):
        value = (values[key] or "").strip()
        if value and not _COLOR.fullmatch(value):
            raise HTTPException(status_code=422, detail=key + "_invalid")
        values[key] = value or None
    if values["support_phone"] is not None:
        values["support_phone"] = values["support_phone"].strip() or None
    return values


def _contact(db: Session, reseller_id: int) -> CentralAppContact | None:
    return db.get(CentralAppContact, int(reseller_id))


def _contact_out(row: CentralAppContact | None) -> dict:
    return {
        field: getattr(row, field, None) if row else None
        for field in ContactIn.model_fields
    }


def _save_contact(db: Session, reseller_id: int, payload: ContactIn) -> dict:
    clean = _clean_contact(payload)
    row = _contact(db, reseller_id)
    if row is None:
        row = CentralAppContact(reseller_id=int(reseller_id))
        db.add(row)
    for key, value in clean.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _contact_out(row)


@router.get("/admin/info")
def admin_client_info(
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    namespace = installation_namespace(ensure_installation_id())
    return {
        "namespace": namespace,
        "app_enabled": central_app_entitled(),
        "registered": None,  # Registration status is vendor-authoritative.
        "reseller_count": db.query(Reseller).count(),
    }


@router.post("/admin/register")
def register_with_vendor(
    payload: RegisterIn,
    _=Depends(require_admin),
):
    if not central_app_entitled():
        raise HTTPException(status_code=403, detail="CENTRAL_APP_NOT_INCLUDED")
    state = load_license_state()
    token = str(state.get("signed_entitlement") or "").strip()
    installation_id = ensure_installation_id()
    try:
        result = _vendor_post(
            "/v1/app/register",
            {
                "installation_id": installation_id,
                "signed_entitlement": token,
                "api_origin": payload.api_origin,
            },
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail="VENDOR_REGISTRATION_REJECTED",
        ) from exc
    except (httpx.TimeoutException, httpx.NetworkError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="VENDOR_UNREACHABLE") from exc
    if result.get("namespace") != installation_namespace(installation_id):
        raise HTTPException(status_code=502, detail="VENDOR_NAMESPACE_MISMATCH")
    return {
        "ok": True, "namespace": result["namespace"],
        "api_origin": result.get("api_origin"),
    }


@router.get("/admin/profile")
def admin_app_profile(
    _=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _contact_out(_contact(db, 0))


@router.put("/admin/profile")
def update_admin_app_profile(
    payload: ContactIn,
    _=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return _save_contact(db, 0, payload)


@router.get("/reseller/profile")
def reseller_app_profile(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    return {
        **_contact_out(_contact(db, reseller.id)),
        "app_username_prefix": reseller_prefix(
            ensure_installation_id(), int(reseller.id)
        ),
        "brand_name": reseller.brand_name or reseller.name,
    }


@router.put("/reseller/profile")
def update_reseller_app_profile(
    payload: ContactIn,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    return {
        **_save_contact(db, int(reseller.id), payload),
        "app_username_prefix": reseller_prefix(
            ensure_installation_id(), int(reseller.id)
        ),
    }


@router.get("/public/brand/{token}")
def subscription_app_brand(
    token: str, db: Session = Depends(get_db),
):
    if not central_app_entitled():
        raise HTTPException(status_code=403, detail="CENTRAL_APP_NOT_INCLUDED")

    sub = _subscription_from_share_token(token, db)
    link = (
        db.query(ResellerSubscription)
        .filter(ResellerSubscription.subscription_id == sub.id)
        .first()
    )
    reseller: Reseller | None = None
    if link:
        reseller = db.get(Reseller, int(link.reseller_id))
        if not reseller or not reseller.is_active:
            raise HTTPException(status_code=403, detail="RESELLER_INACTIVE")

    contact = _contact(db, reseller.id if reseller else 0)
    info = _contact_out(contact)
    if reseller:
        return {
            "namespace": installation_namespace(ensure_installation_id()),
            "owner_type": "reseller",
            "brand_name": reseller.brand_name or reseller.name,
            "logo_url": info["logo_url"],
            "primary_color": info["primary_color"] or "#7C3AED",
            "secondary_color": info["secondary_color"] or "#4F46E5",
            "telegram_url": info["telegram_url"],
            "renewal_url": info["renewal_url"],
            "support_phone": info["support_phone"] or reseller.phone,
            "support_text": reseller.support_text,
            "website_url": info["website_url"],
            "app_username_prefix": reseller_prefix(
                ensure_installation_id(), int(reseller.id)
            ),
        }

    branding = db.query(BrandingSettings).first()
    return {
        "namespace": installation_namespace(ensure_installation_id()),
        "owner_type": "admin",
        "brand_name": getattr(branding, "brand_name", None) or "TwinPanel",
        "logo_url": info["logo_url"] or getattr(branding, "logo_url", None),
        "primary_color": info["primary_color"] or getattr(branding, "primary_color", None) or "#7C3AED",
        "secondary_color": info["secondary_color"] or getattr(branding, "secondary_color", None) or "#4F46E5",
        "telegram_url": info["telegram_url"] or getattr(branding, "telegram_url", None),
        "renewal_url": info["renewal_url"],
        "support_phone": info["support_phone"],
        "support_text": None,
        "website_url": info["website_url"],
        "app_username_prefix": installation_namespace(ensure_installation_id()) + "_A_",
    }
