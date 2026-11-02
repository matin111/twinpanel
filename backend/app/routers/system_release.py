from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import require_admin
from .. import system_release as release
from ..release_manifest_v25 import (
    invalidate_release_manifest_cache,
    refresh_release_manifest_cache,
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


def _admin_license_state(payload: dict) -> dict:
    result = dict(payload)
    result["renewal_bot_url"] = str(
        os.getenv("TWINPANEL_LICENSE_RENEWAL_BOT_URL", "")
    ).strip()
    return result


@router.get("/release/status")
def admin_release_status():
    # Fast path: release_manifest_v25 serves a fresh cache immediately, or a
    # stale last-known-good value while one background refresh runs. Admin page
    # navigation therefore never waits on a slow/filtered GitHub route.
    result = release.release_status(refresh_license_state=False)
    result = dict(result)
    result["license"] = _admin_license_state(dict(result.get("license") or {}))
    return result


@router.post("/release/check")
def admin_release_check():
    # Explicit admin action means a real provider refresh. Keep the last known
    # good manifest available during the attempt, but synchronously use the
    # larger slow-network budget before building the response.
    invalidate_release_manifest_cache()
    refresh_release_manifest_cache()
    result = release.release_status(refresh_license_state=True)
    result = dict(result)
    result["license"] = _admin_license_state(dict(result.get("license") or {}))
    return result


@router.post("/update")
def admin_start_update():
    try:
        # Do not let a stale navigation cache suppress a newly published
        # release. Starting an update always refreshes the release provider first.
        refresh_release_manifest_cache()
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
    return _admin_license_state(release.load_license_state())


@router.post("/license/validate")
def admin_license_validate():
    return _admin_license_state(release.validate_license())


@router.post("/license/trial")
def admin_license_trial():
    try:
        return _admin_license_state(release.start_trial())
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/license/activate")
def admin_license_activate(payload: LicenseActivateIn):
    try:
        return _admin_license_state(release.activate_license(payload.license_key))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
