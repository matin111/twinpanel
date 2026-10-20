from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..branding_models import BrandingSettings
from ..database import get_db
from ..models import User, UserRole
from ..routers.auth import get_current_user


router = APIRouter(
    prefix="/v1/settings/branding",
    tags=["branding"],
)

COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
SAFE_ASSET_RE = re.compile(r"^(?:logo|favicon)-[a-f0-9]{24}\.(?:png|jpe?g|webp|ico)$")
MANAGED_ASSET_PREFIX = "/v1/settings/branding/assets/"
MAX_LOGO_BYTES = 4 * 1024 * 1024
MAX_FAVICON_BYTES = 1024 * 1024

LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
FAVICON_EXTENSIONS = {".png", ".ico", ".webp"}
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}


def _storage_dir() -> Path:
    root = Path(
        os.getenv(
            "TWINPANEL_BRANDING_STORAGE",
            "/var/lib/twinpanel/branding",
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin_only")


def _get_or_create(db: Session) -> BrandingSettings:
    item = db.query(BrandingSettings).first()
    if item:
        return item

    item = BrandingSettings(
        brand_name="Twin Panel",
        site_title="Twin Panel",
        primary_color="#7C3AED",
        secondary_color="#4F46E5",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _normalize_color(value: object, field: str) -> str:
    color = str(value or "").strip()
    if not COLOR_RE.fullmatch(color):
        raise HTTPException(
            status_code=422,
            detail=f"{field}_must_be_hex_color",
        )
    return color.upper()


def _asset_url(filename: str) -> str:
    return f"{MANAGED_ASSET_PREFIX}{filename}"


def _managed_filename(value: str | None) -> str | None:
    if not value or not value.startswith(MANAGED_ASSET_PREFIX):
        return None
    filename = value[len(MANAGED_ASSET_PREFIX) :]
    if not SAFE_ASSET_RE.fullmatch(filename):
        return None
    return filename


def _delete_managed_asset(value: str | None) -> None:
    filename = _managed_filename(value)
    if not filename:
        return
    try:
        (_storage_dir() / filename).unlink(missing_ok=True)
    except OSError:
        pass


def _valid_image_signature(extension: str, blob: bytes) -> bool:
    if extension == ".png":
        return blob.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return blob.startswith(b"\xff\xd8\xff")
    if extension == ".webp":
        return len(blob) >= 12 and blob[:4] == b"RIFF" and blob[8:12] == b"WEBP"
    if extension == ".ico":
        return blob.startswith(b"\x00\x00\x01\x00")
    return False


@router.get("")
def branding(db: Session = Depends(get_db)):
    return _get_or_create(db)


@router.put("")
def update_branding(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    item = _get_or_create(db)

    if "brand_name" in payload:
        brand_name = str(payload.get("brand_name") or "").strip()
        if not brand_name:
            raise HTTPException(status_code=422, detail="brand_name_required")
        item.brand_name = brand_name[:120]

    if "primary_color" in payload:
        item.primary_color = _normalize_color(
            payload.get("primary_color"),
            "primary_color",
        )

    if "secondary_color" in payload:
        item.secondary_color = _normalize_color(
            payload.get("secondary_color"),
            "secondary_color",
        )

    # Compatibility fields remain writable for existing integrations, but the
    # 2027 Branding screen only owns product identity and theme assets. Public
    # storefront copy/contact/footer/SEO stay under /v1/storefront/settings.
    for field, limit in (
        ("logo_url", 500),
        ("favicon_url", 500),
        ("site_title", 200),
        ("telegram_url", 500),
    ):
        if field in payload:
            value = str(payload.get(field) or "").strip()
            setattr(item, field, value[:limit] or None)

    for field in ("site_description", "footer_text"):
        if field in payload:
            value = str(payload.get(field) or "").strip()
            setattr(item, field, value[:4000] or None)

    db.commit()
    db.refresh(item)
    return item


@router.post("/assets/{kind}")
async def upload_branding_asset(
    kind: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)

    kind = str(kind or "").strip().lower()
    if kind not in {"logo", "favicon"}:
        raise HTTPException(status_code=404, detail="branding_asset_not_found")

    original = Path(str(file.filename or "")).name
    extension = Path(original).suffix.lower()
    allowed = LOGO_EXTENSIONS if kind == "logo" else FAVICON_EXTENSIONS
    max_bytes = MAX_LOGO_BYTES if kind == "logo" else MAX_FAVICON_BYTES

    if extension not in allowed:
        raise HTTPException(status_code=422, detail="branding_asset_type_not_allowed")

    blob = await file.read(max_bytes + 1)
    if not blob:
        raise HTTPException(status_code=422, detail="branding_asset_empty")
    if len(blob) > max_bytes:
        raise HTTPException(status_code=413, detail="branding_asset_too_large")
    if not _valid_image_signature(extension, blob):
        raise HTTPException(status_code=422, detail="branding_asset_invalid_image")

    filename = f"{kind}-{secrets.token_hex(12)}{extension}"
    path = _storage_dir() / filename
    path.write_bytes(blob)

    item = _get_or_create(db)
    field = "logo_url" if kind == "logo" else "favicon_url"
    old_value = getattr(item, field)
    setattr(item, field, _asset_url(filename))

    try:
        db.commit()
        db.refresh(item)
    except Exception:
        db.rollback()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    _delete_managed_asset(old_value)
    return item


@router.delete("/assets/{kind}")
def delete_branding_asset(
    kind: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)

    kind = str(kind or "").strip().lower()
    if kind not in {"logo", "favicon"}:
        raise HTTPException(status_code=404, detail="branding_asset_not_found")

    item = _get_or_create(db)
    field = "logo_url" if kind == "logo" else "favicon_url"
    old_value = getattr(item, field)
    setattr(item, field, None)
    db.commit()
    db.refresh(item)
    _delete_managed_asset(old_value)
    return item


@router.get("/assets/{filename}")
def branding_asset(filename: str):
    if not SAFE_ASSET_RE.fullmatch(filename):
        raise HTTPException(status_code=404, detail="branding_asset_not_found")

    path = _storage_dir() / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="branding_asset_not_found")

    extension = path.suffix.lower()
    return FileResponse(
        path=str(path),
        media_type=MEDIA_TYPES.get(extension, "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
