from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

APP_NAME = "TwinPanel Vendor License Center"
ISSUER = "twinpanel-license"
AUDIENCE = "twinpanel"

DATABASE_URL = os.getenv("VENDOR_LICENSE_DATABASE_URL", "sqlite:///./vendor-license.db")
ADMIN_TOKEN = os.getenv("VENDOR_LICENSE_ADMIN_TOKEN", "").strip()
PRIVATE_KEY_FILE = os.getenv("VENDOR_LICENSE_PRIVATE_KEY_FILE", "/etc/twinpanel-vendor/license-private.pem")
DEFAULT_TRIAL_DAYS = int(os.getenv("VENDOR_LICENSE_TRIAL_DAYS", "7"))
ENFORCE_SOURCE_IP = os.getenv("VENDOR_LICENSE_ENFORCE_SOURCE_IP", "0").strip().lower() in {"1", "true", "yes", "on"}

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Plan(Base):
    __tablename__ = "license_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, default=0)
    max_nodes: Mapped[int] = mapped_column(Integer, default=1)
    max_resellers: Mapped[int] = mapped_column(Integer, default=0)
    edition: Mapped[str] = mapped_column(String(64), default="standard")
    release_channel: Mapped[str] = mapped_column(String(32), default="stable")
    features: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class License(Base):
    __tablename__ = "licenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    license_key: Mapped[str] = mapped_column(String(96), unique=True, index=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(160), default="")
    plan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="licensed")
    edition: Mapped[str] = mapped_column(String(64), default="standard")
    release_channel: Mapped[str] = mapped_column(String(32), default="stable")
    features: Mapped[list[str]] = mapped_column(JSON, default=list)
    server_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    installation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    machine_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str] = mapped_column(String(1000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(engine)
app = FastAPI(title=APP_NAME, version="1.0")


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(authorization: str | None = Header(default=None)) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="VENDOR_ADMIN_TOKEN_NOT_CONFIGURED")
    if authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")


def private_key() -> str:
    try:
        with open(PRIVATE_KEY_FILE, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="VENDOR_PRIVATE_KEY_MISSING") from exc


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def iso(value: datetime | None) -> str | None:
    return aware(value).astimezone(timezone.utc).isoformat() if value is not None else None


def normalize_status(item: License) -> str:
    if item.status in {"suspended", "revoked"}:
        return item.status
    expires_at = aware(item.expires_at)
    if item.edition == "trial":
        if expires_at <= now():
            return "trial_expired"
        if expires_at <= now() + timedelta(days=2):
            return "trial_expiring"
        return "trial_active"
    if expires_at <= now():
        return "license_expired"
    if expires_at <= now() + timedelta(days=7):
        return "license_expiring"
    return "licensed"


def sign_entitlement(item: License) -> str:
    expires_at = aware(item.expires_at)
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": f"license:{item.id}",
        "iat": int(now().timestamp()),
        "exp": int(expires_at.timestamp()),
        "status": normalize_status(item),
        "edition": item.edition,
        "release_channel": item.release_channel,
        "features": item.features or [],
        "installation_id": item.installation_id,
        "expires_at": iso(expires_at),
    }
    return jwt.encode(payload, private_key(), algorithm="RS256")


def entitlement_response(item: License) -> dict[str, Any]:
    expires_at = aware(item.expires_at)
    remaining = max(0, int((expires_at - now()).total_seconds()))
    result = {
        "status": normalize_status(item),
        "edition": item.edition,
        "release_channel": item.release_channel,
        "expires_at": iso(expires_at),
        "seconds_remaining": remaining,
        "features": item.features or [],
        "signed_entitlement": sign_entitlement(item),
    }
    if item.edition == "trial":
        result["trial_started_at"] = iso(item.starts_at)
        result["trial_expires_at"] = iso(expires_at)
    return result


def source_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def validate_binding(item: License, installation_id: str, machine_fingerprint: str, request: Request) -> None:
    if item.status in {"revoked", "suspended"}:
        raise HTTPException(status_code=403, detail=item.status.upper())
    if aware(item.expires_at) <= now():
        raise HTTPException(status_code=402, detail="LICENSE_EXPIRED")
    if item.installation_id and item.installation_id != installation_id:
        raise HTTPException(status_code=409, detail="INSTALLATION_MISMATCH")
    if item.machine_fingerprint and item.machine_fingerprint != machine_fingerprint:
        raise HTTPException(status_code=409, detail="FINGERPRINT_MISMATCH")
    if ENFORCE_SOURCE_IP and item.server_ip and source_ip(request) != item.server_ip:
        raise HTTPException(status_code=409, detail="SERVER_IP_MISMATCH")


class PlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    duration_days: int = Field(ge=1, le=3650)
    price: int = Field(default=0, ge=0)
    max_nodes: int = Field(default=1, ge=1)
    max_resellers: int = Field(default=0, ge=0)
    edition: str = "standard"
    release_channel: str = "stable"
    features: list[str] = Field(default_factory=list)
    active: bool = True


class ManualLicenseIn(BaseModel):
    customer_name: str = Field(default="", max_length=160)
    plan_id: int | None = None
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    server_ip: str | None = Field(default=None, max_length=64)
    installation_id: str | None = Field(default=None, max_length=128)
    edition: str | None = None
    release_channel: str | None = None
    features: list[str] | None = None
    notes: str = Field(default="", max_length=1000)


class RenewIn(BaseModel):
    days: int = Field(ge=1, le=3650)


class StatusIn(BaseModel):
    status: str


class ActivateIn(BaseModel):
    license_key: str = Field(min_length=8, max_length=256)
    installation_id: str = Field(min_length=1, max_length=128)
    machine_fingerprint: str = Field(min_length=1, max_length=128)
    product: str = "TwinPanel"
    version: str = ""


class ValidateIn(BaseModel):
    installation_id: str = Field(min_length=1, max_length=128)
    machine_fingerprint: str = Field(min_length=1, max_length=128)
    product: str = "TwinPanel"
    version: str = ""
    signed_entitlement: str | None = None


class TrialIn(BaseModel):
    installation_id: str = Field(min_length=1, max_length=128)
    machine_fingerprint: str = Field(min_length=1, max_length=128)
    product: str = "TwinPanel"
    version: str = ""


@app.get("/health")
def health():
    return {"ok": True, "service": APP_NAME}


@app.get("/v1/admin/plans", dependencies=[Depends(require_admin)])
def list_plans(db: Session = Depends(db_session)):
    return [{"id": item.id, "name": item.name, "duration_days": item.duration_days, "price": item.price, "max_nodes": item.max_nodes, "max_resellers": item.max_resellers, "edition": item.edition, "release_channel": item.release_channel, "features": item.features or [], "active": item.active} for item in db.scalars(select(Plan).order_by(Plan.id.desc())).all()]


@app.post("/v1/admin/plans", dependencies=[Depends(require_admin)])
def create_plan(payload: PlanIn, db: Session = Depends(db_session)):
    item = Plan(**payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="PLAN_NAME_EXISTS") from exc
    db.refresh(item)
    return {"id": item.id, "name": item.name}


@app.get("/v1/admin/licenses", dependencies=[Depends(require_admin)])
def list_licenses(db: Session = Depends(db_session)):
    items = db.scalars(select(License).order_by(License.id.desc())).all()
    return [{"id": item.id, "license_key": item.license_key, "customer_name": item.customer_name, "plan_id": item.plan_id, "status": normalize_status(item), "server_ip": item.server_ip, "installation_id": item.installation_id, "expires_at": iso(item.expires_at), "edition": item.edition, "features": item.features or [], "notes": item.notes} for item in items]


@app.post("/v1/admin/licenses/manual", dependencies=[Depends(require_admin)])
def create_manual_license(payload: ManualLicenseIn, db: Session = Depends(db_session)):
    plan = db.get(Plan, payload.plan_id) if payload.plan_id else None
    if payload.plan_id and not plan:
        raise HTTPException(status_code=404, detail="PLAN_NOT_FOUND")
    duration = payload.duration_days or (plan.duration_days if plan else 30)
    item = License(license_key="TP-" + secrets.token_hex(16).upper(), customer_name=payload.customer_name, plan_id=plan.id if plan else None, status="licensed", edition=payload.edition or (plan.edition if plan else "standard"), release_channel=payload.release_channel or (plan.release_channel if plan else "stable"), features=payload.features if payload.features is not None else ((plan.features or []) if plan else []), server_ip=payload.server_ip, installation_id=payload.installation_id, starts_at=now(), expires_at=now() + timedelta(days=duration), notes=payload.notes)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "license_key": item.license_key, "status": normalize_status(item), "expires_at": iso(item.expires_at)}


@app.post("/v1/admin/licenses/{license_id}/renew", dependencies=[Depends(require_admin)])
def renew_license(license_id: int, payload: RenewIn, db: Session = Depends(db_session)):
    item = db.get(License, license_id)
    if not item:
        raise HTTPException(status_code=404, detail="LICENSE_NOT_FOUND")
    current_expiry = aware(item.expires_at)
    base = current_expiry if current_expiry > now() else now()
    item.expires_at = base + timedelta(days=payload.days)
    if item.status not in {"suspended", "revoked"}:
        item.status = "licensed"
    db.commit()
    return {"id": item.id, "status": normalize_status(item), "expires_at": iso(item.expires_at)}


@app.post("/v1/admin/licenses/{license_id}/status", dependencies=[Depends(require_admin)])
def change_status(license_id: int, payload: StatusIn, db: Session = Depends(db_session)):
    if payload.status not in {"licensed", "suspended", "revoked"}:
        raise HTTPException(status_code=422, detail="INVALID_STATUS")
    item = db.get(License, license_id)
    if not item:
        raise HTTPException(status_code=404, detail="LICENSE_NOT_FOUND")
    item.status = payload.status
    db.commit()
    return {"id": item.id, "status": normalize_status(item)}


@app.post("/v1/license/activate")
def activate(payload: ActivateIn, request: Request, db: Session = Depends(db_session)):
    item = db.scalar(select(License).where(License.license_key == payload.license_key))
    if not item:
        raise HTTPException(status_code=404, detail="LICENSE_NOT_FOUND")
    validate_binding(item, payload.installation_id, payload.machine_fingerprint, request)
    if not item.installation_id:
        item.installation_id = payload.installation_id
    if not item.machine_fingerprint:
        item.machine_fingerprint = payload.machine_fingerprint
    db.commit()
    db.refresh(item)
    return entitlement_response(item)


@app.post("/v1/license/validate")
def validate(payload: ValidateIn, request: Request, db: Session = Depends(db_session)):
    item = db.scalar(select(License).where(License.installation_id == payload.installation_id))
    if not item:
        raise HTTPException(status_code=404, detail="LICENSE_NOT_FOUND")
    validate_binding(item, payload.installation_id, payload.machine_fingerprint, request)
    return entitlement_response(item)


@app.post("/v1/license/trial")
def trial(payload: TrialIn, db: Session = Depends(db_session)):
    existing = db.scalar(select(License).where(License.installation_id == payload.installation_id))
    if existing:
        return entitlement_response(existing)
    item = License(license_key="TRIAL-" + secrets.token_hex(12).upper(), customer_name="Trial", status="licensed", edition="trial", release_channel="stable", features=["trial"], installation_id=payload.installation_id, machine_fingerprint=payload.machine_fingerprint, starts_at=now(), expires_at=now() + timedelta(days=DEFAULT_TRIAL_DAYS), notes="Automatic trial")
    db.add(item)
    db.commit()
    db.refresh(item)
    return entitlement_response(item)
