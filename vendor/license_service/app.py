from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

PRODUCT = "twinpanel"
ISSUER = "twinpanel-license"
AUDIENCE = "twinpanel"
TRIAL_DAYS = 7
EXPIRING_SECONDS = 3 * 86400
ENTITLEMENT_TOKEN_SECONDS = 6 * 3600
DOWNLOAD_TOKEN_SECONDS = 10 * 60

DATABASE_URL = os.getenv(
    "TWINPANEL_LICENSE_DATABASE_URL",
    "sqlite:////var/lib/twinpanel-license-server/license.db",
).strip()
RELEASE_ROOT = Path(
    os.getenv(
        "TWINPANEL_LICENSE_RELEASE_ROOT",
        "/srv/twinpanel-releases",
    )
)
PRIVATE_KEY_FILE = Path(
    os.getenv(
        "TWINPANEL_LICENSE_PRIVATE_KEY_FILE",
        "/etc/twinpanel-license-server/signing-private.pem",
    )
)
PUBLIC_KEY_FILE = Path(
    os.getenv(
        "TWINPANEL_LICENSE_PUBLIC_KEY_FILE",
        "/etc/twinpanel-license-server/signing-public.pem",
    )
)
PUBLIC_BASE_URL = os.getenv("TWINPANEL_LICENSE_PUBLIC_BASE_URL", "").strip().rstrip("/")
KEY_PEPPER = os.getenv("TWINPANEL_LICENSE_KEY_PEPPER", "").strip()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def seconds_until(value: datetime | None) -> int | None:
    value = aware(value)
    if value is None:
        return None
    return int((value - utcnow()).total_seconds())


def normalize_installation_id(value: str) -> str:
    value = str(value or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{20,64}", value):
        raise HTTPException(422, "INVALID_INSTALLATION_ID")
    return value.lower()


def normalize_fingerprint(value: str) -> str:
    value = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise HTTPException(422, "INVALID_MACHINE_FINGERPRINT")
    return value


def normalize_license_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())


def hash_license_key(value: str) -> str:
    normalized = normalize_license_key(value)
    material = f"{KEY_PEPPER}:{normalized}" if KEY_PEPPER else normalized
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def signing_private_key() -> str:
    if not PRIVATE_KEY_FILE.is_file():
        raise RuntimeError("LICENSE_PRIVATE_KEY_MISSING")
    return PRIVATE_KEY_FILE.read_text(encoding="utf-8")


def signing_public_key() -> str:
    if not PUBLIC_KEY_FILE.is_file():
        raise RuntimeError("LICENSE_PUBLIC_KEY_MISSING")
    return PUBLIC_KEY_FILE.read_text(encoding="utf-8")


def base_url(request: Request) -> str:
    return PUBLIC_BASE_URL or str(request.base_url).rstrip("/")


class Base(DeclarativeBase):
    pass


class Installation(Base):
    __tablename__ = "installations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    installation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), index=True)
    product: Mapped[str] = mapped_column(String(32), default=PRODUCT)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    current_version: Mapped[str] = mapped_column(String(64), default="0.0.0")
    release_channel: Mapped[str] = mapped_column(String(32), default="stable")


class Trial(Base):
    __tablename__ = "trials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="active")
    reset_count: Mapped[int] = mapped_column(Integer, default=0)


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    key_hint: Mapped[str] = mapped_column(String(32), default="")
    customer_ref: Mapped[str] = mapped_column(String(160), default="")
    edition: Mapped[str] = mapped_column(String(32), default="standard")
    status: Mapped[str] = mapped_column(String(32), default="active")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_installations: Mapped[int] = mapped_column(Integer, default=1)
    release_channel: Mapped[str] = mapped_column(String(32), default="stable")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Activation(Base):
    __tablename__ = "activations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_id: Mapped[int] = mapped_column(ForeignKey("licenses.id"), index=True)
    installation_id: Mapped[str] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LicenseEvent(Base):
    __tablename__ = "license_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    installation_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    license_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base.metadata.create_all(engine)


class InstallationIn(BaseModel):
    installation_id: str = Field(min_length=20, max_length=64)
    machine_fingerprint: str = Field(min_length=64, max_length=64)
    product: str = "TwinPanel"
    version: str = "0.0.0"


class TrialIn(InstallationIn):
    pass


class ActivateIn(InstallationIn):
    license_key: str = Field(min_length=8, max_length=256)


class ValidateIn(InstallationIn):
    signed_entitlement: str | None = None


class ResolveInstallIn(BaseModel):
    product: str = "TwinPanel"
    installation_id: str = Field(min_length=20, max_length=64)
    machine_fingerprint: str = Field(min_length=64, max_length=64)
    license_key: str | None = None
    requested_channel: str = "stable"
    updater_version: int = 1


class ReleaseIn(BaseModel):
    installation_id: str = Field(min_length=20, max_length=64)
    signed_entitlement: str | None = None
    current_version: str = "0.0.0"
    requested_version: str | None = None
    channel: str = "stable"


def event(
    db: Session,
    event_type: str,
    installation_id: str = "",
    license_id: int | None = None,
    **detail: Any,
) -> None:
    db.add(
        LicenseEvent(
            event_type=event_type,
            installation_id=installation_id,
            license_id=license_id,
            detail=json.dumps(detail, ensure_ascii=False, sort_keys=True),
        )
    )


def ensure_installation(
    db: Session,
    installation_id: str,
    fingerprint: str,
    version: str,
    channel: str,
) -> Installation:
    installation_id = normalize_installation_id(installation_id)
    fingerprint = normalize_fingerprint(fingerprint)
    row = db.scalar(select(Installation).where(Installation.installation_id == installation_id))
    if row is None:
        row = Installation(
            installation_id=installation_id,
            fingerprint_hash=fingerprint,
            current_version=str(version or "0.0.0")[:64],
            release_channel=str(channel or "stable")[:32],
        )
        db.add(row)
        db.flush()
        event(db, "installation_created", installation_id, fingerprint=fingerprint[:12])
    else:
        if row.fingerprint_hash != fingerprint:
            raise HTTPException(409, "INSTALLATION_FINGERPRINT_MISMATCH")
        row.last_seen_at = utcnow()
        row.current_version = str(version or row.current_version or "0.0.0")[:64]
        row.release_channel = str(channel or row.release_channel or "stable")[:32]
    return row


def current_paid(db: Session, installation_id: str) -> tuple[License, Activation] | None:
    rows = db.execute(
        select(License, Activation)
        .join(Activation, Activation.license_id == License.id)
        .where(
            Activation.installation_id == installation_id,
            Activation.active.is_(True),
        )
        .order_by(Activation.id.desc())
    ).all()
    for license_row, activation in rows:
        if license_row.status in {"revoked", "suspended"}:
            return license_row, activation
        expires = aware(license_row.expires_at)
        if expires is None or expires > utcnow():
            return license_row, activation
        return license_row, activation
    return None


def state_for(db: Session, installation: Installation) -> dict[str, Any]:
    paid = current_paid(db, installation.installation_id)
    if paid:
        license_row, activation = paid
        activation.last_validated_at = utcnow()
        if license_row.status == "revoked":
            status = "revoked"
        elif license_row.status == "suspended":
            status = "suspended"
        else:
            remaining = seconds_until(license_row.expires_at)
            if remaining is not None and remaining <= 0:
                status = "license_expired"
            elif remaining is not None and remaining <= EXPIRING_SECONDS:
                status = "license_expiring"
            else:
                status = "licensed"
        return {
            "status": status,
            "edition": license_row.edition,
            "release_channel": license_row.release_channel,
            "expires_at": iso(license_row.expires_at),
            "seconds_remaining": seconds_until(license_row.expires_at),
            "license_id": license_row.id,
        }

    trial = db.scalar(select(Trial).where(Trial.fingerprint_hash == installation.fingerprint_hash))
    if trial is None:
        return {
            "status": "trial_missing",
            "edition": "trial",
            "release_channel": installation.release_channel or "stable",
            "seconds_remaining": 0,
        }

    remaining = seconds_until(trial.expires_at) or 0
    if trial.status == "revoked":
        status = "revoked"
    elif remaining <= 0:
        status = "trial_expired"
    elif remaining <= EXPIRING_SECONDS:
        status = "trial_expiring"
    else:
        status = "trial_active"

    return {
        "status": status,
        "edition": "trial",
        "release_channel": installation.release_channel or "stable",
        "trial_started_at": iso(trial.started_at),
        "trial_expires_at": iso(trial.expires_at),
        "seconds_remaining": remaining,
    }


def sign_entitlement(installation: Installation, state: dict[str, Any]) -> str:
    now = utcnow()
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ENTITLEMENT_TOKEN_SECONDS)).timestamp()),
        "scope": "entitlement",
        "product": PRODUCT,
        "installation_id": installation.installation_id,
        "fingerprint_hash": installation.fingerprint_hash,
        "status": state.get("status"),
        "edition": state.get("edition", "standard"),
        "release_channel": state.get("release_channel", "stable"),
        "expires_at": state.get("expires_at"),
        "trial_started_at": state.get("trial_started_at"),
        "trial_expires_at": state.get("trial_expires_at"),
    }
    return jwt.encode(claims, signing_private_key(), algorithm="RS256")


def output_state(installation: Installation, state: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "installation_id": installation.installation_id,
        "signed_entitlement": sign_entitlement(installation, state),
    }


def start_or_recover_trial(db: Session, installation: Installation) -> dict[str, Any]:
    paid = current_paid(db, installation.installation_id)
    if paid:
        return state_for(db, installation)

    trial = db.scalar(select(Trial).where(Trial.fingerprint_hash == installation.fingerprint_hash))
    if trial is None:
        started = utcnow()
        trial = Trial(
            fingerprint_hash=installation.fingerprint_hash,
            started_at=started,
            expires_at=started + timedelta(days=TRIAL_DAYS),
            status="active",
        )
        db.add(trial)
        db.flush()
        event(db, "trial_started", installation.installation_id, expires_at=iso(trial.expires_at))
    else:
        event(db, "trial_recovered", installation.installation_id, expires_at=iso(trial.expires_at))
    return state_for(db, installation)


def activate_paid(db: Session, installation: Installation, raw_key: str) -> dict[str, Any]:
    key_hash = hash_license_key(raw_key)
    license_row = db.scalar(select(License).where(License.key_hash == key_hash))
    if license_row is None:
        raise HTTPException(404, "LICENSE_KEY_NOT_FOUND")
    if license_row.status != "active":
        raise HTTPException(409, f"LICENSE_{license_row.status.upper()}")
    if aware(license_row.starts_at) and aware(license_row.starts_at) > utcnow():
        raise HTTPException(409, "LICENSE_NOT_STARTED")
    if aware(license_row.expires_at) and aware(license_row.expires_at) <= utcnow():
        raise HTTPException(409, "LICENSE_EXPIRED")

    existing = db.scalar(
        select(Activation).where(
            Activation.license_id == license_row.id,
            Activation.installation_id == installation.installation_id,
            Activation.active.is_(True),
        )
    )
    if existing is None:
        count = len(
            db.scalars(
                select(Activation).where(
                    Activation.license_id == license_row.id,
                    Activation.active.is_(True),
                )
            ).all()
        )
        if count >= int(license_row.max_installations or 1):
            raise HTTPException(409, "LICENSE_ACTIVATION_LIMIT")

        for other in db.scalars(
            select(Activation).where(
                Activation.installation_id == installation.installation_id,
                Activation.active.is_(True),
            )
        ).all():
            other.active = False
            other.deactivated_at = utcnow()

        existing = Activation(
            license_id=license_row.id,
            installation_id=installation.installation_id,
            active=True,
            activated_at=utcnow(),
            last_validated_at=utcnow(),
        )
        db.add(existing)
        event(db, "license_activated", installation.installation_id, license_row.id)
    else:
        existing.last_validated_at = utcnow()
        event(db, "license_reactivated", installation.installation_id, license_row.id)

    db.flush()
    return state_for(db, installation)


def release_metadata(channel: str) -> dict[str, Any]:
    safe_channel = re.sub(r"[^a-z0-9_-]", "", str(channel or "stable").lower()) or "stable"
    path = RELEASE_ROOT / f"{safe_channel}.json"
    if not path.is_file():
        raise HTTPException(503, "RELEASE_NOT_PUBLISHED")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(503, "RELEASE_METADATA_INVALID") from exc
    if not isinstance(value, dict) or value.get("installable") is not True:
        raise HTTPException(503, "RELEASE_NOT_INSTALLABLE")
    filename = Path(str(value.get("file") or "")).name
    sha256 = str(value.get("sha256") or "").strip().lower()
    version = str(value.get("version") or "").strip()
    if not filename or not version or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise HTTPException(503, "RELEASE_METADATA_INCOMPLETE")
    package = RELEASE_ROOT / filename
    if not package.is_file():
        raise HTTPException(503, "RELEASE_PACKAGE_MISSING")
    return {**value, "file": filename, "sha256": sha256, "version": version}


def download_token(installation: Installation, metadata: dict[str, Any]) -> str:
    now = utcnow()
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=DOWNLOAD_TOKEN_SECONDS)).timestamp()),
        "scope": "release-download",
        "installation_id": installation.installation_id,
        "file": metadata["file"],
        "sha256": metadata["sha256"],
        "version": metadata["version"],
    }
    return jwt.encode(claims, signing_private_key(), algorithm="RS256")


def release_output(request: Request, installation: Installation, state: dict[str, Any]) -> dict[str, Any]:
    if state.get("status") not in {"trial_active", "trial_expiring", "licensed", "license_expiring"}:
        raise HTTPException(402, state.get("status") or "LICENSE_REQUIRED")
    metadata = release_metadata(str(state.get("release_channel") or "stable"))
    token = download_token(installation, metadata)
    return {
        "version": metadata["version"],
        "channel": metadata.get("channel") or state.get("release_channel") or "stable",
        "package_url": f"{base_url(request)}/v1/download/{token}",
        "download_url": f"{base_url(request)}/v1/download/{token}",
        "sha256": metadata["sha256"],
        "released_at": metadata.get("released_at"),
        "notes": metadata.get("notes") or {},
    }


app = FastAPI(title="TwinPanel License Service", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "TwinPanel License Service", "version": "1.0.0"}


@app.post("/v1/install/resolve")
def install_resolve(payload: ResolveInstallIn, request: Request) -> dict[str, Any]:
    with SessionLocal() as db:
        installation = ensure_installation(
            db,
            payload.installation_id,
            payload.machine_fingerprint,
            "0.0.0",
            payload.requested_channel,
        )
        state = (
            activate_paid(db, installation, payload.license_key)
            if payload.license_key
            else start_or_recover_trial(db, installation)
        )
        if state.get("status") not in {"trial_active", "trial_expiring", "licensed", "license_expiring"}:
            db.commit()
            raise HTTPException(402, state.get("status") or "LICENSE_REQUIRED")
        signed = output_state(installation, state)
        release = release_output(request, installation, state)
        event(db, "install_resolved", installation.installation_id, version=release["version"], status=state["status"])
        db.commit()
        return {
            "ok": True,
            **signed,
            **release,
            "license_state": state["status"],
            "license_public_key_pem": signing_public_key(),
        }


@app.post("/v1/license/trial")
def license_trial(payload: TrialIn) -> dict[str, Any]:
    with SessionLocal() as db:
        installation = ensure_installation(
            db,
            payload.installation_id,
            payload.machine_fingerprint,
            payload.version,
            "stable",
        )
        state = start_or_recover_trial(db, installation)
        event(db, "trial_checked", installation.installation_id, status=state["status"])
        db.commit()
        return output_state(installation, state)


@app.post("/v1/license/activate")
def license_activate(payload: ActivateIn) -> dict[str, Any]:
    with SessionLocal() as db:
        installation = ensure_installation(
            db,
            payload.installation_id,
            payload.machine_fingerprint,
            payload.version,
            "stable",
        )
        state = activate_paid(db, installation, payload.license_key)
        db.commit()
        return output_state(installation, state)


@app.post("/v1/license/validate")
def license_validate(payload: ValidateIn) -> dict[str, Any]:
    with SessionLocal() as db:
        installation = ensure_installation(
            db,
            payload.installation_id,
            payload.machine_fingerprint,
            payload.version,
            "stable",
        )
        state = state_for(db, installation)
        event(db, "license_validated", installation.installation_id, status=state["status"])
        db.commit()
        return output_state(installation, state)


@app.post("/v1/license/release")
def license_release(payload: ReleaseIn, request: Request) -> dict[str, Any]:
    installation_id = normalize_installation_id(payload.installation_id)
    with SessionLocal() as db:
        installation = db.scalar(select(Installation).where(Installation.installation_id == installation_id))
        if installation is None:
            raise HTTPException(404, "INSTALLATION_NOT_FOUND")
        state = state_for(db, installation)
        result = release_output(request, installation, state)
        event(db, "release_resolved", installation.installation_id, version=result["version"], status=state["status"])
        db.commit()
        return result


@app.get("/v1/releases/latest")
def releases_latest(channel: str = "stable") -> dict[str, Any]:
    metadata = release_metadata(channel)
    return {
        "product": "TwinPanel",
        "channel": metadata.get("channel") or channel,
        "version": metadata["version"],
        "released_at": metadata.get("released_at"),
        "notes": metadata.get("notes") or {},
        "sha256": metadata["sha256"],
    }


@app.get("/v1/download/{token}")
def release_download(token: str) -> FileResponse:
    try:
        claims = jwt.decode(
            token,
            signing_public_key(),
            algorithms=["RS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise HTTPException(401, "INVALID_DOWNLOAD_TOKEN") from exc
    if claims.get("scope") != "release-download":
        raise HTTPException(403, "INVALID_DOWNLOAD_SCOPE")
    filename = Path(str(claims.get("file") or "")).name
    if not filename:
        raise HTTPException(404, "RELEASE_FILE_MISSING")
    package = RELEASE_ROOT / filename
    if not package.is_file():
        raise HTTPException(404, "RELEASE_FILE_NOT_FOUND")
    expected = str(claims.get("sha256") or "").lower()
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    if not secrets.compare_digest(digest, expected):
        raise HTTPException(409, "RELEASE_FILE_HASH_MISMATCH")
    return FileResponse(
        package,
        media_type="application/gzip",
        filename=filename,
        headers={"Cache-Control": "private, no-store"},
    )
