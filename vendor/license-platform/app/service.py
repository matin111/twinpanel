from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Installation, LicenseAuditEvent, PaidLicense, Release, TrialIdentity
from .schemas import AdminLicenseCreateIn, AdminReleaseRegisterIn, InstallResolveIn
from .security import (
    generate_license_key,
    hash_license_key,
    public_key,
    sign_download_token,
    sign_entitlement,
    utc_now,
    verify_entitlement,
)
from .settings import settings


ACTIVE_PAID_STATES = {"active"}
ACTIVE_ENTITLEMENT_STATES = {
    "trial_active",
    "trial_expiring",
    "licensed",
    "license_expiring",
}


def _fingerprint_hash(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64,128}", raw):
        raise ValueError("MACHINE_FINGERPRINT_INVALID")
    material = f"{settings.license_key_pepper}|fingerprint|{raw}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_key(value: str) -> tuple[int, int, int, int, int]:
    raw = str(value or "").strip().lower().lstrip("v")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:[-.]?([a-z]+)[.-]?(\d*)?)?", raw)
    if not match:
        return (0, 0, 0, -1, 0)
    major, minor, patch = [int(match.group(i) or 0) for i in (1, 2, 3)]
    label = match.group(4) or ""
    number = int(match.group(5) or 0)
    rank = {
        "": 4,
        "stable": 4,
        "release": 4,
        "rc": 3,
        "beta": 2,
        "preview": 1,
        "alpha": 1,
        "dev": 0,
    }.get(label, 0)
    return (major, minor, patch, rank, number)


def _audit(
    db: Session,
    event_type: str,
    *,
    installation_id: str | None = None,
    fingerprint_hash: str | None = None,
    paid_license_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        LicenseAuditEvent(
            event_type=event_type,
            installation_id=installation_id,
            fingerprint_hash=fingerprint_hash,
            paid_license_id=paid_license_id,
            payload=payload or {},
            created_at=utc_now(),
        )
    )


def _installation(
    db: Session,
    *,
    installation_id: str,
    machine_fingerprint: str,
    version: str | None = None,
) -> tuple[Installation, str]:
    installation_id = str(installation_id or "").strip()
    if len(installation_id) < 8 or len(installation_id) > 64:
        raise ValueError("INSTALLATION_ID_INVALID")

    fingerprint_hash = _fingerprint_hash(machine_fingerprint)
    now = utc_now()
    row = db.scalar(
        select(Installation).where(Installation.installation_id == installation_id)
    )
    if row is None:
        row = Installation(
            installation_id=installation_id,
            fingerprint_hash=fingerprint_hash,
            first_seen_at=now,
            last_seen_at=now,
            last_version=version,
            revoked=False,
        )
        db.add(row)
        db.flush()
        _audit(
            db,
            "installation_created",
            installation_id=installation_id,
            fingerprint_hash=fingerprint_hash,
        )
    elif row.fingerprint_hash != fingerprint_hash:
        raise ValueError("INSTALLATION_FINGERPRINT_MISMATCH")
    elif row.revoked:
        raise ValueError("INSTALLATION_REVOKED")
    else:
        row.last_seen_at = now
        if version:
            row.last_version = version

    return row, fingerprint_hash


def _trial_row(db: Session, fingerprint_hash: str, *, create: bool) -> TrialIdentity | None:
    row = db.scalar(
        select(TrialIdentity).where(TrialIdentity.fingerprint_hash == fingerprint_hash)
    )
    if row is None and create:
        now = utc_now()
        row = TrialIdentity(
            fingerprint_hash=fingerprint_hash,
            trial_started_at=now,
            trial_expires_at=now + timedelta(days=settings.trial_days),
            reset_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        _audit(db, "trial_created", fingerprint_hash=fingerprint_hash)
    return row


def _trial_status(row: TrialIdentity) -> tuple[str, int]:
    remaining = int((row.trial_expires_at - utc_now()).total_seconds())
    if remaining <= 0:
        return "trial_expired", max(0, remaining)
    if remaining <= 3 * 86400:
        return "trial_expiring", remaining
    return "trial_active", remaining


def _paid_status(row: PaidLicense) -> tuple[str, int | None]:
    if row.status == "revoked":
        return "revoked", 0
    if row.status == "suspended":
        return "suspended", 0
    if row.status not in ACTIVE_PAID_STATES:
        return "license_expired", 0

    if row.expires_at is None:
        return "licensed", None

    remaining = int((row.expires_at - utc_now()).total_seconds())
    if remaining <= 0:
        return "license_expired", max(0, remaining)
    if remaining <= 7 * 86400:
        return "license_expiring", remaining
    return "licensed", remaining


def _entitlement_payload(
    *,
    installation: Installation,
    status: str,
    release_channel: str,
    edition: str = "standard",
    expires_at: datetime | None = None,
    trial_started_at: datetime | None = None,
    trial_expires_at: datetime | None = None,
    seconds_remaining: int | None = None,
    features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    claims = {
        "scope": "twinpanel_entitlement",
        "status": status,
        "installation_id": installation.installation_id,
        "edition": edition,
        "release_channel": release_channel,
        "features": features or {},
        "license_expires_at": expires_at.isoformat() if expires_at else None,
        "trial_started_at": trial_started_at.isoformat() if trial_started_at else None,
        "trial_expires_at": trial_expires_at.isoformat() if trial_expires_at else None,
    }
    token = sign_entitlement(claims)
    return {
        "ok": True,
        "status": status,
        "installation_id": installation.installation_id,
        "edition": edition,
        "release_channel": release_channel,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "trial_started_at": trial_started_at.isoformat() if trial_started_at else None,
        "trial_expires_at": trial_expires_at.isoformat() if trial_expires_at else None,
        "seconds_remaining": seconds_remaining,
        "features": features or {},
        "signed_entitlement": token,
    }


def start_or_recover_trial(
    db: Session,
    *,
    installation_id: str,
    machine_fingerprint: str,
    version: str,
) -> dict[str, Any]:
    installation, fp = _installation(
        db,
        installation_id=installation_id,
        machine_fingerprint=machine_fingerprint,
        version=version,
    )
    if installation.paid_license_id:
        return validate_installation(
            db,
            installation_id=installation_id,
            machine_fingerprint=machine_fingerprint,
            version=version,
        )

    trial = _trial_row(db, fp, create=True)
    assert trial is not None
    status, remaining = _trial_status(trial)
    _audit(
        db,
        "trial_resolved",
        installation_id=installation.installation_id,
        fingerprint_hash=fp,
        payload={"status": status},
    )
    db.commit()
    return _entitlement_payload(
        installation=installation,
        status=status,
        release_channel=settings.default_release_channel,
        trial_started_at=trial.trial_started_at,
        trial_expires_at=trial.trial_expires_at,
        seconds_remaining=remaining,
    )


def activate_paid_license(
    db: Session,
    *,
    license_key: str,
    installation_id: str,
    machine_fingerprint: str,
    version: str,
) -> dict[str, Any]:
    installation, fp = _installation(
        db,
        installation_id=installation_id,
        machine_fingerprint=machine_fingerprint,
        version=version,
    )
    key_hash = hash_license_key(license_key)
    license_row = db.scalar(
        select(PaidLicense).where(PaidLicense.key_hash == key_hash)
    )
    if license_row is None:
        raise ValueError("LICENSE_KEY_NOT_FOUND")

    status, remaining = _paid_status(license_row)
    if status not in {"licensed", "license_expiring"}:
        raise ValueError(status.upper())

    if license_row.activation_fingerprint_hash is None:
        license_row.activation_fingerprint_hash = fp
    elif license_row.activation_fingerprint_hash != fp:
        raise ValueError("LICENSE_ALREADY_ACTIVATED_ON_ANOTHER_MACHINE")

    installation.paid_license_id = license_row.id
    installation.last_seen_at = utc_now()
    _audit(
        db,
        "license_activated",
        installation_id=installation.installation_id,
        fingerprint_hash=fp,
        paid_license_id=license_row.id,
    )
    db.commit()
    return _entitlement_payload(
        installation=installation,
        status=status,
        release_channel=license_row.release_channel,
        edition=license_row.edition,
        expires_at=license_row.expires_at,
        seconds_remaining=remaining,
        features=license_row.features,
    )


def validate_installation(
    db: Session,
    *,
    installation_id: str,
    machine_fingerprint: str,
    version: str,
) -> dict[str, Any]:
    installation, fp = _installation(
        db,
        installation_id=installation_id,
        machine_fingerprint=machine_fingerprint,
        version=version,
    )

    if installation.paid_license_id:
        paid = db.get(PaidLicense, installation.paid_license_id)
        if paid is not None:
            status, remaining = _paid_status(paid)
            _audit(
                db,
                "license_validated",
                installation_id=installation.installation_id,
                fingerprint_hash=fp,
                paid_license_id=paid.id,
                payload={"status": status},
            )
            db.commit()
            return _entitlement_payload(
                installation=installation,
                status=status,
                release_channel=paid.release_channel,
                edition=paid.edition,
                expires_at=paid.expires_at,
                seconds_remaining=remaining,
                features=paid.features,
            )

    trial = _trial_row(db, fp, create=False)
    if trial is None:
        db.commit()
        return _entitlement_payload(
            installation=installation,
            status="trial_expired",
            release_channel=settings.default_release_channel,
            seconds_remaining=0,
        )

    status, remaining = _trial_status(trial)
    _audit(
        db,
        "trial_validated",
        installation_id=installation.installation_id,
        fingerprint_hash=fp,
        payload={"status": status},
    )
    db.commit()
    return _entitlement_payload(
        installation=installation,
        status=status,
        release_channel=settings.default_release_channel,
        trial_started_at=trial.trial_started_at,
        trial_expires_at=trial.trial_expires_at,
        seconds_remaining=remaining,
    )


def _resolve_release_row(
    db: Session,
    *,
    channel: str,
    requested_version: str | None = None,
) -> Release:
    query = select(Release).where(
        Release.channel == channel,
        Release.installable.is_(True),
    )
    rows = list(db.scalars(query).all())
    if requested_version:
        rows = [row for row in rows if row.version == requested_version]
    if not rows:
        raise ValueError("NO_INSTALLABLE_RELEASE")
    return max(rows, key=lambda row: _version_key(row.version))


def resolve_release(
    db: Session,
    *,
    installation_id: str,
    signed_entitlement: str,
    channel: str,
    requested_version: str | None = None,
    updater_version: int | None = None,
) -> dict[str, Any]:
    claims = verify_entitlement(signed_entitlement)
    if claims.get("scope") != "twinpanel_entitlement":
        raise ValueError("INVALID_ENTITLEMENT_SCOPE")
    if claims.get("installation_id") != installation_id:
        raise ValueError("ENTITLEMENT_INSTALLATION_MISMATCH")
    status = str(claims.get("status") or "")
    if status not in ACTIVE_ENTITLEMENT_STATES:
        raise ValueError("LICENSE_REQUIRED")

    entitled_channel = str(claims.get("release_channel") or settings.default_release_channel)
    if channel and channel != entitled_channel:
        raise ValueError("RELEASE_CHANNEL_NOT_ENTITLED")

    release = _resolve_release_row(
        db,
        channel=entitled_channel,
        requested_version=requested_version,
    )
    if updater_version is not None and updater_version < release.minimum_updater_version:
        raise ValueError("UPDATER_TOO_OLD")

    package_path = (settings.release_root / release.package_filename).resolve()
    release_root = settings.release_root.resolve()
    if release_root != package_path and release_root not in package_path.parents:
        raise ValueError("INVALID_RELEASE_PATH")
    if not package_path.is_file():
        raise ValueError("RELEASE_PACKAGE_MISSING")

    token = sign_download_token(
        installation_id=installation_id,
        version=release.version,
    )
    package_url = (
        f"{settings.public_base_url.rstrip('/')}/v1/release/download/"
        f"{release.version}?token={token}"
    )
    return {
        "ok": True,
        "version": release.version,
        "channel": release.channel,
        "release_channel": release.channel,
        "package_url": package_url,
        "download_url": package_url,
        "sha256": release.sha256,
        "minimum_updater_version": release.minimum_updater_version,
        "notes": {
            "fa": release.notes_fa,
            "en": release.notes_en,
        },
    }


def resolve_install(db: Session, payload: InstallResolveIn) -> dict[str, Any]:
    if payload.license_key:
        entitlement = activate_paid_license(
            db,
            license_key=payload.license_key,
            installation_id=payload.installation_id,
            machine_fingerprint=payload.machine_fingerprint,
            version="0.0.0",
        )
    else:
        entitlement = start_or_recover_trial(
            db,
            installation_id=payload.installation_id,
            machine_fingerprint=payload.machine_fingerprint,
            version="0.0.0",
        )

    release = resolve_release(
        db,
        installation_id=payload.installation_id,
        signed_entitlement=str(entitlement["signed_entitlement"]),
        channel=str(entitlement.get("release_channel") or payload.requested_channel),
        updater_version=payload.updater_version,
    )
    return {
        **entitlement,
        **release,
        "license_state": entitlement.get("status"),
        "entitlement_token": entitlement.get("signed_entitlement"),
        "license_public_key_pem": public_key(),
    }


def issue_license(db: Session, payload: AdminLicenseCreateIn) -> dict[str, Any]:
    now = utc_now()
    raw_key = generate_license_key()
    expires = now + timedelta(days=payload.duration_days) if payload.duration_days else None
    row = PaidLicense(
        key_hash=hash_license_key(raw_key),
        key_prefix=raw_key[:8],
        key_last4=raw_key[-4:],
        status="active",
        edition=payload.edition,
        release_channel=payload.release_channel,
        starts_at=now,
        expires_at=expires,
        activation_fingerprint_hash=None,
        activation_reset_count=0,
        customer_ref=payload.customer_ref,
        notes=payload.notes,
        features=payload.features,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _audit(db, "license_issued", paid_license_id=row.id, payload={"customer_ref": payload.customer_ref})
    db.commit()
    return {
        "ok": True,
        "id": row.id,
        "license_key": raw_key,
        "status": row.status,
        "edition": row.edition,
        "release_channel": row.release_channel,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "warning": "The raw key is returned only at issuance time.",
    }


def register_release(db: Session, payload: AdminReleaseRegisterIn) -> dict[str, Any]:
    filename = Path(payload.package_filename).name
    if filename != payload.package_filename:
        raise ValueError("INVALID_PACKAGE_FILENAME")
    path = (settings.release_root / filename).resolve()
    root = settings.release_root.resolve()
    if root != path and root not in path.parents:
        raise ValueError("INVALID_RELEASE_PATH")
    if not path.is_file():
        raise ValueError("RELEASE_PACKAGE_MISSING")
    actual = _sha256_file(path)
    if actual.lower() != payload.sha256.lower():
        raise ValueError("RELEASE_SHA256_MISMATCH")

    row = db.scalar(
        select(Release).where(
            Release.version == payload.version,
            Release.channel == payload.channel,
        )
    )
    now = utc_now()
    if row is None:
        row = Release(
            version=payload.version,
            channel=payload.channel,
            package_filename=filename,
            sha256=actual,
            minimum_updater_version=payload.minimum_updater_version,
            installable=payload.installable,
            notes_fa=payload.notes_fa,
            notes_en=payload.notes_en,
            published_at=now,
            created_at=now,
        )
        db.add(row)
    else:
        row.package_filename = filename
        row.sha256 = actual
        row.minimum_updater_version = payload.minimum_updater_version
        row.installable = payload.installable
        row.notes_fa = payload.notes_fa
        row.notes_en = payload.notes_en
        row.published_at = now
    db.flush()
    _audit(db, "release_registered", payload={"version": row.version, "channel": row.channel, "installable": row.installable})
    db.commit()
    return {
        "ok": True,
        "version": row.version,
        "channel": row.channel,
        "sha256": row.sha256,
        "installable": row.installable,
    }
