from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_admin
from ..system_release import (
    activate_license,
    load_license_state,
    release_status,
    request_update,
    start_trial,
    validate_license,
)


router = APIRouter(
    prefix="/v1/admin/system",
    tags=["admin-system-release"],
    dependencies=[Depends(require_admin)],
)


class LicenseActivateIn(BaseModel):
    license_key: str = Field(min_length=8, max_length=256)


@router.get("/release/status")
def admin_release_status():
    return release_status(refresh_license_state=False)


@router.post("/release/check")
def admin_release_check():
    return release_status(refresh_license_state=True)


@router.post("/update")
def admin_start_update():
    try:
        return request_update()
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
    return load_license_state()


@router.post("/license/validate")
def admin_license_validate():
    return validate_license()


@router.post("/license/trial")
def admin_license_trial():
    try:
        return start_trial()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/license/activate")
def admin_license_activate(payload: LicenseActivateIn):
    try:
        return activate_license(payload.license_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
