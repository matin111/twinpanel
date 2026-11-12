"""Tenant-isolated logo upload for TwinConnect; public reads, authenticated writes."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..central_app_models import CentralAppContact
from ..database import get_db
from ..deps import require_admin, require_reseller
from ..models_reseller import Reseller

router = APIRouter(prefix="/v1/central-app", tags=["central-app-assets"])
MAX_LOGO_BYTES = 2 * 1024 * 1024
MIME = {".png":"image/png",".jpg":"image/jpeg",".webp":"image/webp"}


def _logo_extension(blob: bytes) -> str | None:
    if blob.startswith(b"\x89PNG\r\n\x1a\n"): return ".png"
    if blob.startswith(b"\xff\xd8\xff"): return ".jpg"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP": return ".webp"
    return None


def _directory() -> Path:
    root = Path(os.getenv("TWINPANEL_APP_BRAND_ASSETS", "/var/lib/twinpanel/app-brand-logos"))
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    return root


async def _upload_logo(db: Session, owner_id: int, request: Request, file: UploadFile) -> dict:
    blob = await file.read(MAX_LOGO_BYTES + 1)
    if len(blob) > MAX_LOGO_BYTES:
        raise HTTPException(413, "LOGO_MAX_2MB")
    if not blob:
        raise HTTPException(422, "LOGO_EMPTY")
    ext = _logo_extension(blob)
    if ext is None:
        raise HTTPException(422, "LOGO_FORMAT_PNG_JPG_WEBP")
    # Digest filename creates immutable, cache-safe URLs without user-provided paths.
    digest = hashlib.sha256(blob).hexdigest()[:24]
    filename = digest + ext
    folder = _directory() / str(owner_id)
    folder.mkdir(mode=0o750, parents=True, exist_ok=True)
    target = folder / filename
    if not target.exists():
        temp = folder / ("." + filename + ".tmp")
        temp.write_bytes(blob)
        temp.chmod(0o644)
        temp.replace(target)
    path = f"/v1/central-app/public/assets/logo/{owner_id}/{filename}"
    # Clients outside the browser need a complete URL; obey proxy-forwarded scheme.
    public_origin = str(request.base_url).rstrip("/")
    if request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https":
        public_origin = "https://" + request.url.netloc
    logo_url = public_origin + path
    record = db.get(CentralAppContact, owner_id)
    if record is None:
        record = CentralAppContact(reseller_id=owner_id)
        db.add(record)
    record.logo_url = logo_url
    db.commit()
    return {"logo_url":logo_url}


@router.post("/admin/assets/logo")
async def admin_logo(
    request: Request, file: UploadFile = File(...),
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    return await _upload_logo(db, 0, request, file)


@router.post("/admin/resellers/{reseller_id}/assets/logo")
async def admin_reseller_logo(
    reseller_id: int, request: Request, file: UploadFile = File(...),
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    if not db.get(Reseller, reseller_id):
        raise HTTPException(404, "RESELLER_NOT_FOUND")
    return await _upload_logo(db, reseller_id, request, file)


@router.post("/reseller/assets/logo")
async def reseller_logo(
    request: Request, file: UploadFile = File(...),
    db: Session = Depends(get_db), reseller: Reseller = Depends(require_reseller),
):
    return await _upload_logo(db, int(reseller.id), request, file)


@router.get("/public/assets/logo/{reseller_id}/{filename}")
def public_logo(reseller_id: int, filename: str):
    # Only hashed names can be read. No arbitrary filesystem path or directory listing.
    import re
    if not re.fullmatch(r"[0-9a-f]{24}\.(png|jpg|webp)", filename):
        raise HTTPException(404, "LOGO_NOT_FOUND")
    path = _directory() / str(reseller_id) / filename
    if not path.is_file():
        raise HTTPException(404, "LOGO_NOT_FOUND")
    return FileResponse(path, media_type=MIME[path.suffix],
                        headers={"Cache-Control":"public, max-age=31536000, immutable",
                                 "X-Content-Type-Options":"nosniff"})
