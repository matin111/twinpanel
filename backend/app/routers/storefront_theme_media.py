from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..models import User, UserRole
from .auth import get_current_user


router = APIRouter(
    prefix="/v1/storefront/settings/media",
    tags=["storefront-theme-media"],
)

MAX_THEME_ASSET_BYTES = 8 * 1024 * 1024
TEMPLATE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}$")
SLOT_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,119}$")
ALLOWED_EXTENSIONS = {".png", ".jpg", ".webp"}
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
}


def _storage_dir() -> Path:
    root = Path(
        os.getenv(
            "TWINPANEL_STOREFRONT_MEDIA_STORAGE",
            "/var/lib/twinpanel/storefront-media",
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="admin_only")


def _clean_component(value: str, pattern: re.Pattern[str], detail: str) -> str:
    cleaned = str(value or "").strip()
    if not pattern.fullmatch(cleaned):
        raise HTTPException(status_code=422, detail=detail)
    return cleaned


def _template_dir(template_id: str) -> Path:
    path = _storage_dir() / template_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _detected_extension(blob: bytes) -> str | None:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if blob.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(blob) >= 12 and blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return ".webp"
    return None


def _managed_path(template_id: str, slot: str) -> Path | None:
    root = _template_dir(template_id)
    for extension in ALLOWED_EXTENSIONS:
        candidate = root / f"{slot}{extension}"
        if candidate.is_file():
            return candidate
    return None


def _delete_managed_asset(template_id: str, slot: str) -> None:
    root = _template_dir(template_id)
    for extension in ALLOWED_EXTENSIONS:
        try:
            (root / f"{slot}{extension}").unlink(missing_ok=True)
        except OSError:
            pass


@router.get("/{template_id}/{slot}")
def storefront_theme_asset(template_id: str, slot: str):
    clean_template = _clean_component(
        template_id,
        TEMPLATE_ID_RE,
        "invalid_template_id",
    )
    clean_slot = _clean_component(slot, SLOT_RE, "invalid_media_slot")
    path = _managed_path(clean_template, clean_slot)
    if not path:
        raise HTTPException(status_code=404, detail="storefront_theme_asset_not_found")

    return FileResponse(
        path=str(path),
        media_type=MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/{template_id}/{slot}")
async def upload_storefront_theme_asset(
    template_id: str,
    slot: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    clean_template = _clean_component(
        template_id,
        TEMPLATE_ID_RE,
        "invalid_template_id",
    )
    clean_slot = _clean_component(slot, SLOT_RE, "invalid_media_slot")

    blob = await file.read(MAX_THEME_ASSET_BYTES + 1)
    if len(blob) > MAX_THEME_ASSET_BYTES:
        raise HTTPException(status_code=413, detail="storefront_theme_asset_too_large")
    if not blob:
        raise HTTPException(status_code=422, detail="storefront_theme_asset_empty")

    extension = _detected_extension(blob)
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail="storefront_theme_asset_invalid_format:jpg,png,webp",
        )

    root = _template_dir(clean_template)
    temporary = root / f".{clean_slot}.{secrets.token_hex(8)}.tmp"
    destination = root / f"{clean_slot}{extension}"
    temporary.write_bytes(blob)

    try:
        _delete_managed_asset(clean_template, clean_slot)
        temporary.replace(destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

    version = secrets.token_hex(6)
    return {
        "template_id": clean_template,
        "slot": clean_slot,
        "url": f"/v1/storefront/settings/media/{clean_template}/{clean_slot}?v={version}",
    }


@router.delete("/{template_id}/{slot}")
def delete_storefront_theme_asset(
    template_id: str,
    slot: str,
    user: User = Depends(get_current_user),
):
    _require_admin(user)
    clean_template = _clean_component(
        template_id,
        TEMPLATE_ID_RE,
        "invalid_template_id",
    )
    clean_slot = _clean_component(slot, SLOT_RE, "invalid_media_slot")
    _delete_managed_asset(clean_template, clean_slot)
    return {
        "template_id": clean_template,
        "slot": clean_slot,
        "deleted": True,
    }
