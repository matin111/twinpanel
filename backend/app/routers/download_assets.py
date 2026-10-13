from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..download_asset_models import DownloadAsset


admin_router = APIRouter(
    prefix="/v1/admin/download-assets",
    tags=["download-assets"],
    dependencies=[Depends(require_admin)],
)

public_router = APIRouter(
    prefix="/v1/public-downloads",
    tags=["public-download-assets"],
)

PLATFORMS = {"windows", "macos", "android", "ios", "linux"}
PROTOCOLS = {"cisco", "openvpn", "wireguard", "l2tp", "v2ray", "other"}
ALLOWED_EXTENSIONS = {
    ".apk", ".aab", ".msi", ".exe", ".zip", ".dmg", ".pkg",
    ".deb", ".rpm", ".appimage", ".ovpn", ".conf", ".txt", ".pdf",
}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def storage_dir() -> Path:
    root = Path(
        os.getenv(
            "TWINPANEL_DOWNLOAD_STORAGE",
            "/var/lib/twinpanel/downloads",
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_original_name(value: str) -> str:
    name = Path(str(value or "download.bin")).name
    name = re.sub(r"[^A-Za-z0-9._()\- +]", "_", name).strip(" .")
    return name[:180] or "download.bin"


def asset_path(asset: DownloadAsset) -> Path:
    return storage_dir() / asset.storage_name


def asset_out(asset: DownloadAsset) -> dict:
    exists = asset_path(asset).is_file()
    return {
        "id": asset.id,
        "platform": asset.platform,
        "protocol": asset.protocol,
        "name": asset.name,
        "note": asset.note,
        "original_filename": asset.original_filename,
        "content_type": asset.content_type,
        "file_size": int(asset.file_size or 0),
        "sort_order": int(asset.sort_order or 100),
        "is_active": bool(asset.is_active),
        "file_exists": exists,
        "download_url": f"/v1/public-downloads/{asset.id}" if exists and asset.is_active else None,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
    }


def public_downloads_by_platform(db: Session) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {key: [] for key in PLATFORMS}
    rows = (
        db.query(DownloadAsset)
        .filter(DownloadAsset.is_active.is_(True))
        .order_by(DownloadAsset.platform.asc(), DownloadAsset.sort_order.asc(), DownloadAsset.id.asc())
        .all()
    )
    for asset in rows:
        if asset.platform not in result:
            continue
        if not asset_path(asset).is_file():
            continue
        result[asset.platform].append(
            {
                "id": asset.id,
                "name": asset.name,
                "note": asset.note or "",
                "protocol": asset.protocol,
                "url": f"/v1/public-downloads/{asset.id}",
                "file_size": int(asset.file_size or 0),
            }
        )
    return result


@admin_router.get("")
def list_assets(db: Session = Depends(get_db)):
    rows = (
        db.query(DownloadAsset)
        .order_by(DownloadAsset.platform.asc(), DownloadAsset.sort_order.asc(), DownloadAsset.id.desc())
        .all()
    )
    return {
        "items": [asset_out(row) for row in rows],
        "storage_dir": str(storage_dir()),
        "platforms": sorted(PLATFORMS),
        "protocols": sorted(PROTOCOLS),
    }


@admin_router.post("")
async def upload_asset(
    platform: str = Form(...),
    name: str = Form(...),
    protocol: str = Form("other"),
    note: str = Form(""),
    sort_order: int = Form(100),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    platform = str(platform or "").strip().lower()
    protocol = str(protocol or "other").strip().lower()
    name = str(name or "").strip()
    note = str(note or "").strip()

    if platform not in PLATFORMS:
        raise HTTPException(status_code=422, detail="سیستم عامل معتبر نیست")
    if protocol not in PROTOCOLS:
        raise HTTPException(status_code=422, detail="پروتکل معتبر نیست")
    if not name:
        raise HTTPException(status_code=422, detail="نام فایل الزامی است")

    original = safe_original_name(file.filename or "download.bin")
    extension = Path(original).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="پسوند فایل مجاز نیست")

    blob = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(blob) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="حجم فایل بیشتر از 500MB است")
    if not blob:
        raise HTTPException(status_code=422, detail="فایل خالی است")

    storage_name = f"{secrets.token_hex(16)}{extension}"
    path = storage_dir() / storage_name
    path.write_bytes(blob)

    asset = DownloadAsset(
        platform=platform,
        protocol=protocol,
        name=name[:180],
        note=note[:300] or None,
        original_filename=original,
        storage_name=storage_name,
        content_type=(file.content_type or "application/octet-stream")[:120],
        file_size=len(blob),
        sort_order=int(sort_order),
        is_active=True,
    )

    try:
        db.add(asset)
        db.commit()
        db.refresh(asset)
    except Exception:
        db.rollback()
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        raise

    return asset_out(asset)


@admin_router.patch("/{asset_id}")
def update_asset(asset_id: int, payload: dict, db: Session = Depends(get_db)):
    asset = db.get(DownloadAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="فایل پیدا نشد")

    if "name" in payload:
        value = str(payload.get("name") or "").strip()
        if not value:
            raise HTTPException(status_code=422, detail="نام فایل الزامی است")
        asset.name = value[:180]

    if "note" in payload:
        value = str(payload.get("note") or "").strip()
        asset.note = value[:300] or None

    if "sort_order" in payload:
        asset.sort_order = int(payload.get("sort_order") or 100)

    if "is_active" in payload:
        asset.is_active = bool(payload.get("is_active"))

    db.commit()
    db.refresh(asset)
    return asset_out(asset)


@admin_router.delete("/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(DownloadAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="فایل پیدا نشد")

    path = asset_path(asset)
    db.delete(asset)
    db.commit()
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True, "id": asset_id}


@public_router.get("/{asset_id}")
def download_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(DownloadAsset, asset_id)
    if not asset or not asset.is_active:
        raise HTTPException(status_code=404, detail="فایل پیدا نشد")

    path = asset_path(asset)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="فایل روی سرور موجود نیست")

    return FileResponse(
        path=str(path),
        media_type=asset.content_type or "application/octet-stream",
        filename=asset.original_filename,
    )
