from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_admin
from .. import system_release as release
from ..release_manifest_v25 import (
    invalidate_release_manifest_cache,
    release_manifest_v25,
)


# Install the resilient manifest resolver before any route calls release_status
# or request_update. Both functions resolve release.release_manifest at runtime,
# so status checks and update requests use the exact same provider chain.
release.release_manifest = release_manifest_v25


router = APIRouter(
    prefix="/v1/admin/system",
    tags=["admin-system-release"],
    dependencies=[Depends(require_admin)],
)


class LicenseActivateIn(BaseModel):
    license_key: str = Field(min_length=8, max_length=256)


@router.get("/release/status")
def admin_release_status():
    # Fast path: release_manifest_v25 serves the short-lived manifest cache.
    # This route is polled by the admin nav and must not repeatedly block on
    # GitHub/provider latency.
    return release.release_status(refresh_license_state=False)


@router.post("/release/check")
def admin_release_check():
    # Explicit admin action always means a real provider refresh. Once this
    # succeeds, subsequent status/nav reads are immediate from the shared cache.
    invalidate_release_manifest_cache()
    return release.release_status(refresh_license_state=True)


@router.post("/update")
def admin_start_update():
    try:
        return release.request_update()
    except RuntimeError as exc:
        message = str(exc)
        status_code = 409
        if message in {
            "LICENSE_REQUIRED_FOR_UPDATE",
            "LICENSE_API_NOT_CONFIGURED",
            "LICENSE_PUBLIC_KEY_MISSING",
        }:
            status_code = 402
        raise HTTPException(status_code=status_code, detail=message) from exc


@router.get("/license")
def admin_license_status():
    return release.load_license_state()


@router.post("/license/validate")
def admin_license_validate():
    return release.validate_license()


@router.post("/license/trial")
def admin_license_trial():
    try:
        return release.start_trial()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/license/activate")
def admin_license_activate(payload: LicenseActivateIn):
    try:
        return release.activate_license(payload.license_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
