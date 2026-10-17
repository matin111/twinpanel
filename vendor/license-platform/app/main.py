from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Installation, PaidLicense, Release, TrialIdentity
from .schemas import (
    ActivateIn,
    AdminLicenseCreateIn,
    AdminLicenseExtendIn,
    AdminReleaseRegisterIn,
    AdminReleaseToggleIn,
    AdminTrialResetIn,
    InstallResolveIn,
    ReleaseResolveIn,
    TrialIn,
    ValidateIn,
)
from .security import hash_license_key, utc_now, verify_admin_token, verify_download_token
from .service import (
    activate_paid_license,
    issue_license,
    register_release,
    resolve_install,
    resolve_release,
    start_or_recover_trial,
    validate_installation,
)
from .settings import settings


Base.metadata.create_all(bind=engine)
settings.release_root.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
)


def admin_auth(x_admin_token: str | None = Header(default=None)) -> None:
    if not verify_admin_token(x_admin_token):
        raise HTTPException(status_code=401, detail="VENDOR_ADMIN_AUTH_REQUIRED")


def as_http_error(exc: Exception) -> HTTPException:
    detail = str(exc) or type(exc).__name__
    mapping = {
        "LICENSE_KEY_NOT_FOUND": 404,
        "RELEASE_PACKAGE_MISSING": 404,
        "NO_INSTALLABLE_RELEASE": 404,
        "LICENSE_REQUIRED": 402,
        "TRIAL_EXPIRED": 402,
        "LICENSE_EXPIRED": 402,
        "LICENSE_ALREADY_ACTIVATED_ON_ANOTHER_MACHINE": 409,
        "INSTALLATION_FINGERPRINT_MISMATCH": 409,
        "UPDATER_TOO_OLD": 426,
    }
    return HTTPException(status_code=mapping.get(detail, 400), detail=detail)


@app.get("/health")
def health():
    return {"ok": True, "service": settings.app_name, "version": "1.0.0"}


@app.post("/v1/install/resolve")
def install_resolve(payload: InstallResolveIn, db: Session = Depends(get_db)):
    try:
        return resolve_install(db, payload)
    except Exception as exc:
        db.rollback()
        raise as_http_error(exc) from exc


@app.post("/v1/license/trial")
def license_trial(payload: TrialIn, db: Session = Depends(get_db)):
    try:
        return start_or_recover_trial(
            db,
            installation_id=payload.installation_id,
            machine_fingerprint=payload.machine_fingerprint,
            version=payload.version,
        )
    except Exception as exc:
        db.rollback()
        raise as_http_error(exc) from exc


@app.post("/v1/license/activate")
def license_activate(payload: ActivateIn, db: Session = Depends(get_db)):
    try:
        return activate_paid_license(
            db,
            license_key=payload.license_key,
            installation_id=payload.installation_id,
            machine_fingerprint=payload.machine_fingerprint,
            version=payload.version,
        )
    except Exception as exc:
        db.rollback()
        raise as_http_error(exc) from exc


@app.post("/v1/license/validate")
def license_validate(payload: ValidateIn, db: Session = Depends(get_db)):
    try:
        return validate_installation(
            db,
            installation_id=payload.installation_id,
            machine_fingerprint=payload.machine_fingerprint,
            version=payload.version,
        )
    except Exception as exc:
        db.rollback()
        raise as_http_error(exc) from exc


@app.post("/v1/license/release")
def license_release(payload: ReleaseResolveIn, db: Session = Depends(get_db)):
    try:
        return resolve_release(
            db,
            installation_id=payload.installation_id,
            signed_entitlement=payload.signed_entitlement,
            channel=payload.channel,
            requested_version=payload.requested_version,
        )
    except Exception as exc:
        db.rollback()
        raise as_http_error(exc) from exc


@app.get("/v1/release/download/{version}")
def release_download(
    version: str,
    token: str = Query(min_length=40),
    db: Session = Depends(get_db),
):
    try:
        verify_download_token(token, version=version)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    rows = list(
        db.scalars(
            select(Release).where(
                Release.version == version,
                Release.installable.is_(True),
            )
        ).all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="RELEASE_NOT_FOUND")
    row = rows[0]
    path = (settings.release_root / row.package_filename).resolve()
    root = settings.release_root.resolve()
    if (root != path and root not in path.parents) or not path.is_file():
        raise HTTPException(status_code=404, detail="RELEASE_PACKAGE_MISSING")
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=row.package_filename,
        headers={"Cache-Control": "private, no-store"},
    )


@app.post("/v1/vendor/licenses", dependencies=[Depends(admin_auth)])
def vendor_issue_license(payload: AdminLicenseCreateIn, db: Session = Depends(get_db)):
    try:
        return issue_license(db, payload)
    except Exception as exc:
        db.rollback()
        raise as_http_error(exc) from exc


@app.get("/v1/vendor/licenses", dependencies=[Depends(admin_auth)])
def vendor_list_licenses(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(PaidLicense).order_by(PaidLicense.id.desc()).limit(500)).all())
    return {
        "items": [
            {
                "id": row.id,
                "key": f"{row.key_prefix}…{row.key_last4}",
                "status": row.status,
                "edition": row.edition,
                "release_channel": row.release_channel,
                "starts_at": row.starts_at.isoformat(),
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "activated": bool(row.activation_fingerprint_hash),
                "customer_ref": row.customer_ref,
            }
            for row in rows
        ]
    }


@app.post("/v1/vendor/licenses/{license_id}/extend", dependencies=[Depends(admin_auth)])
def vendor_extend_license(license_id: int, payload: AdminLicenseExtendIn, db: Session = Depends(get_db)):
    row = db.get(PaidLicense, license_id)
    if row is None:
        raise HTTPException(status_code=404, detail="LICENSE_NOT_FOUND")
    base = row.expires_at if row.expires_at and row.expires_at > utc_now() else utc_now()
    row.expires_at = base + timedelta(days=payload.days)
    row.status = "active"
    row.updated_at = utc_now()
    db.commit()
    return {"ok": True, "id": row.id, "expires_at": row.expires_at.isoformat()}


@app.post("/v1/vendor/licenses/{license_id}/{action}", dependencies=[Depends(admin_auth)])
def vendor_license_action(license_id: int, action: str, db: Session = Depends(get_db)):
    row = db.get(PaidLicense, license_id)
    if row is None:
        raise HTTPException(status_code=404, detail="LICENSE_NOT_FOUND")
    if action == "suspend":
        row.status = "suspended"
    elif action == "activate":
        row.status = "active"
    elif action == "revoke":
        row.status = "revoked"
    elif action == "reset-activation":
        row.activation_fingerprint_hash = None
        row.activation_reset_count = int(row.activation_reset_count or 0) + 1
    else:
        raise HTTPException(status_code=404, detail="UNKNOWN_LICENSE_ACTION")
    row.updated_at = utc_now()
    db.commit()
    return {"ok": True, "id": row.id, "status": row.status, "activation_reset_count": row.activation_reset_count}


@app.post("/v1/vendor/trials/reset", dependencies=[Depends(admin_auth)])
def vendor_reset_trial(payload: AdminTrialResetIn, db: Session = Depends(get_db)):
    row = db.scalar(select(TrialIdentity).where(TrialIdentity.fingerprint_hash == payload.fingerprint_hash))
    if row is None:
        raise HTTPException(status_code=404, detail="TRIAL_IDENTITY_NOT_FOUND")
    now = utc_now()
    row.trial_started_at = now
    row.trial_expires_at = now + timedelta(days=settings.trial_days)
    row.reset_count = int(row.reset_count or 0) + 1
    row.updated_at = now
    db.commit()
    return {
        "ok": True,
        "fingerprint_hash": row.fingerprint_hash,
        "trial_started_at": row.trial_started_at.isoformat(),
        "trial_expires_at": row.trial_expires_at.isoformat(),
        "reset_count": row.reset_count,
        "reason": payload.reason,
    }


@app.post("/v1/vendor/releases", dependencies=[Depends(admin_auth)])
def vendor_register_release(payload: AdminReleaseRegisterIn, db: Session = Depends(get_db)):
    try:
        return register_release(db, payload)
    except Exception as exc:
        db.rollback()
        raise as_http_error(exc) from exc


@app.get("/v1/vendor/releases", dependencies=[Depends(admin_auth)])
def vendor_list_releases(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Release).order_by(Release.id.desc()).limit(200)).all())
    return {
        "items": [
            {
                "id": row.id,
                "version": row.version,
                "channel": row.channel,
                "sha256": row.sha256,
                "package_filename": row.package_filename,
                "installable": row.installable,
                "minimum_updater_version": row.minimum_updater_version,
                "published_at": row.published_at.isoformat(),
            }
            for row in rows
        ]
    }


@app.put("/v1/vendor/releases/{release_id}/installable", dependencies=[Depends(admin_auth)])
def vendor_release_toggle(release_id: int, payload: AdminReleaseToggleIn, db: Session = Depends(get_db)):
    row = db.get(Release, release_id)
    if row is None:
        raise HTTPException(status_code=404, detail="RELEASE_NOT_FOUND")
    row.installable = payload.installable
    db.commit()
    return {"ok": True, "id": row.id, "version": row.version, "installable": row.installable}


@app.get("/v1/vendor/installations", dependencies=[Depends(admin_auth)])
def vendor_installations(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Installation).order_by(Installation.id.desc()).limit(500)).all())
    return {
        "items": [
            {
                "id": row.id,
                "installation_id": row.installation_id,
                "fingerprint_hash": row.fingerprint_hash,
                "paid_license_id": row.paid_license_id,
                "first_seen_at": row.first_seen_at.isoformat(),
                "last_seen_at": row.last_seen_at.isoformat(),
                "last_version": row.last_version,
                "revoked": row.revoked,
            }
            for row in rows
        ]
    }
