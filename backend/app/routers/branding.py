from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..branding_models import BrandingSettings
from ..models import User, UserRole
from ..routers.auth import get_current_user


router = APIRouter(
    prefix="/v1/settings/branding",
    tags=["branding"],
)

DEFAULT_BRAND_NAME = "TwinPanel"
DEFAULT_PRIMARY_COLOR = "#7C3AED"
DEFAULT_SECONDARY_COLOR = "#4F46E5"
MAX_BRAND_ASSET_BYTES = 2 * 1024 * 1024
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
MANAGED_ASSET_FIELDS = {
    "logo": "logo_url",
    "favicon": "favicon_url",
}
MANAGED_EXTENSIONS = {
    "logo": {".png", ".jpg", ".jpeg", ".webp"},
    "favicon": {".png", ".webp", ".ico"},
}
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}
UPDATE_FIELDS = {
    "brand_name",
    "logo_url",
    "favicon_url",
    "primary_color",
    "secondary_color",
    "site_title",
    "site_description",
    "footer_text",
    "telegram_url",
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


def _branding_row(db: Session) -> BrandingSettings:
    item = db.query(BrandingSettings).first()
    if item:
        return item

    item = BrandingSettings(
        brand_name=DEFAULT_BRAND_NAME,
        site_title=DEFAULT_BRAND_NAME,
        primary_color=DEFAULT_PRIMARY_COLOR,
        secondary_color=DEFAULT_SECONDARY_COLOR,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin_only")


def _managed_path(kind: str) -> Path | None:
    root = _storage_dir()
    for suffix in MANAGED_EXTENSIONS[kind]:
        candidate = root / f"{kind}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _delete_managed_asset(kind: str) -> None:
    root = _storage_dir()
    for suffix in MANAGED_EXTENSIONS[kind]:
        try:
            (root / f"{kind}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass


def _detected_extension(blob: bytes) -> str | None:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(blob) >= 12 and blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return ".webp"
    if blob.startswith(b"\x00\x00\x01\x00"):
        return ".ico"
    return None


def _clean_nullable_text(value: object, limit: int) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None


def _validate_color(value: object, field: str) -> str:
    color = str(value or "").strip()
    if not COLOR_RE.fullmatch(color):
        raise HTTPException(status_code=422, detail=f"{field}_invalid")
    return color.upper()


@router.get("")
def branding(db: Session = Depends(get_db)):
    return _branding_row(db)


@router.put("")
def update_branding(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    item = _branding_row(db)

    unknown = set(payload) - UPDATE_FIELDS
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"unsupported_fields": sorted(unknown)},
        )

    if "brand_name" in payload:
        brand_name = str(payload.get("brand_name") or "").strip()
        if not brand_name:
            raise HTTPException(status_code=422, detail="brand_name_required")
        item.brand_name = brand_name[:120]

    if "primary_color" in payload:
        item.primary_color = _validate_color(payload.get("primary_color"), "primary_color")

    if "secondary_color" in payload:
        item.secondary_color = _validate_color(payload.get("secondary_color"), "secondary_color")

    if "logo_url" in payload:
        item.logo_url = _clean_nullable_text(payload.get("logo_url"), 500)

    if "favicon_url" in payload:
        item.favicon_url = _clean_nullable_text(payload.get("favicon_url"), 500)

    if "site_title" in payload:
        site_title = str(payload.get("site_title") or "").strip()
        if not site_title:
            raise HTTPException(status_code=422, detail="site_title_required")
        item.site_title = site_title[:200]

    if "site_description" in payload:
        item.site_description = _clean_nullable_text(payload.get("site_description"), 4000)

    if "footer_text" in payload:
        item.footer_text = _clean_nullable_text(payload.get("footer_text"), 4000)

    if "telegram_url" in payload:
        item.telegram_url = _clean_nullable_text(payload.get("telegram_url"), 500)

    db.commit()
    db.refresh(item)
    return item


@router.get("/assets/{kind}")
def branding_asset(kind: str):
    if kind not in MANAGED_ASSET_FIELDS:
        raise HTTPException(status_code=404, detail="branding_asset_not_found")

    path = _managed_path(kind)
    if not path:
        raise HTTPException(status_code=404, detail="branding_asset_not_found")

    return FileResponse(
        path=str(path),
        media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/assets/{kind}")
async def upload_branding_asset(
    kind: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    if kind not in MANAGED_ASSET_FIELDS:
        raise HTTPException(status_code=404, detail="branding_asset_not_found")

    blob = await file.read(MAX_BRAND_ASSET_BYTES + 1)
    if len(blob) > MAX_BRAND_ASSET_BYTES:
        raise HTTPException(status_code=413, detail="branding_asset_too_large")
    if not blob:
        raise HTTPException(status_code=422, detail="branding_asset_empty")

    extension = _detected_extension(blob)
    if extension not in MANAGED_EXTENSIONS[kind]:
        allowed = ",".join(sorted(MANAGED_EXTENSIONS[kind]))
        raise HTTPException(
            status_code=422,
            detail=f"branding_asset_invalid_format:{allowed}",
        )

    root = _storage_dir()
    temporary = root / f".{kind}.{secrets.token_hex(8)}.tmp"
    destination = root / f"{kind}{extension}"
    temporary.write_bytes(blob)

    try:
        _delete_managed_asset(kind)
        temporary.replace(destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

    item = _branding_row(db)
    version = secrets.token_hex(6)
    setattr(
        item,
        MANAGED_ASSET_FIELDS[kind],
        f"/v1/settings/branding/assets/{kind}?v={version}",
    )
    db.commit()
    db.refresh(item)
    return item


@router.delete("/assets/{kind}")
def delete_branding_asset(
    kind: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    if kind not in MANAGED_ASSET_FIELDS:
        raise HTTPException(status_code=404, detail="branding_asset_not_found")

    _delete_managed_asset(kind)
    item = _branding_row(db)
    setattr(item, MANAGED_ASSET_FIELDS[kind], None)
    db.commit()
    db.refresh(item)
    return item
