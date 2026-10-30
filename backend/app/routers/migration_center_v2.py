from __future__ import annotations

import base64
import hashlib
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..migration_import_models import MigrationImportRecord
from ..models import Subscription, User
from ..security import hash_password
from ..services.migration_center_v1 import normalize_record
from ..services.migration_import_v2 import import_record, legacy_payload


MigrationSource = Literal["sanaei", "marzban", "pasargad"]

admin_router = APIRouter(
    prefix="/admin/migration-center",
    tags=["migration-center-v2"],
    dependencies=[Depends(require_admin)],
)

public_router = APIRouter(
    prefix="/v1/migration/legacy",
    tags=["migration-legacy-delivery"],
)


class MigrationImportIn(BaseModel):
    source: MigrationSource
    record: dict[str, Any]
    target_user_id: int
    protocols: list[str] = Field(default_factory=lambda: ["v2ray"], max_length=20)
    traffic_limit_bytes: int = Field(default=0, ge=0)
    traffic_used_bytes: int = Field(default=0, ge=0)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    activation_duration_days: int | None = Field(default=None, ge=1, le=3650)


class MigrationBatchImportIn(BaseModel):
    source: MigrationSource
    records: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    protocols: list[str] = Field(default_factory=lambda: ["v2ray"], max_length=20)


def _migration_owner_email(source: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{source}:{source_id}".encode()).hexdigest()[:32]
    return f"migration-{source}-{digest}@import.invalid"


def _ensure_migration_owner(
    db: Session,
    *,
    source: str,
    source_id: str,
    username: str,
) -> tuple[User, bool]:
    email = _migration_owner_email(source, source_id)
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user, False

    user = User(
        email=email,
        full_name=username[:150] or None,
        password_hash=hash_password("migration-login-disabled"),
        is_active=False,
    )
    db.add(user)
    db.flush()
    return user, True


@admin_router.get("/imports")
def migration_import_history(db: Session = Depends(get_db)):
    markers = (
        db.query(MigrationImportRecord)
        .order_by(MigrationImportRecord.created_at.desc(), MigrationImportRecord.id.desc())
        .limit(500)
        .all()
    )
    items: list[dict[str, Any]] = []
    for marker in markers:
        sub = db.get(Subscription, marker.subscription_id)
        items.append(
            {
                "id": marker.id,
                "source": marker.source,
                "source_id": marker.source_id,
                "subscription_id": marker.subscription_id,
                "user_id": sub.user_id if sub else None,
                "account_username": sub.account_username if sub else None,
                "subscription_status": (
                    getattr(sub.status, "value", str(sub.status)) if sub else "missing"
                ),
                "legacy_url": marker.legacy_url,
                "legacy_token": marker.legacy_token,
                "status": marker.status,
                "created_at": marker.created_at.isoformat() if marker.created_at else None,
            }
        )
    return {"count": len(items), "items": items}


@admin_router.post("/import")
def migration_import(payload: MigrationImportIn, db: Session = Depends(get_db)):
    try:
        return import_record(
            db,
            source=payload.source,
            record=payload.record,
            target_user_id=payload.target_user_id,
            protocols=payload.protocols,
            traffic_limit_bytes=payload.traffic_limit_bytes,
            traffic_used_bytes=payload.traffic_used_bytes,
            starts_at=payload.starts_at,
            expires_at=payload.expires_at,
            activation_duration_days=payload.activation_duration_days,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@admin_router.post("/import-batch")
def migration_import_batch(payload: MigrationBatchImportIn, db: Session = Depends(get_db)):
    imported = 0
    existing = 0
    failed = 0
    auto_created_users = 0
    results: list[dict[str, Any]] = []

    for index, record in enumerate(payload.records):
        try:
            normalized = normalize_record(payload.source, record, index)
            source_id = str(normalized.get("source_id") or "").strip()
            username = str(normalized.get("username") or "").strip()
            if not source_id:
                raise ValueError("source_id is required for idempotent import")
            if not username:
                raise ValueError("username is required for import")

            marker = (
                db.query(MigrationImportRecord)
                .filter(
                    MigrationImportRecord.source == payload.source,
                    MigrationImportRecord.source_id == source_id,
                )
                .first()
            )
            if marker:
                existing += 1
                results.append(
                    {
                        "index": index,
                        "source_id": source_id,
                        "username": username,
                        "imported": False,
                        "idempotent": True,
                        "subscription_id": marker.subscription_id,
                    }
                )
                continue

            user, created_user = _ensure_migration_owner(
                db,
                source=payload.source,
                source_id=source_id,
                username=username,
            )
            result = import_record(
                db,
                source=payload.source,
                record=record,
                target_user_id=user.id,
                protocols=payload.protocols,
                allow_inactive_target=True,
            )
            if result.get("imported"):
                imported += 1
                auto_created_users += 1 if created_user else 0
            elif result.get("idempotent"):
                existing += 1
            results.append(
                {
                    "index": index,
                    "source_id": source_id,
                    "username": username,
                    "user_id": user.id,
                    **result,
                }
            )
        except Exception as exc:
            db.rollback()
            failed += 1
            results.append(
                {
                    "index": index,
                    "source_id": str(record.get("source_id") or record.get("id") or ""),
                    "username": str(record.get("username") or record.get("email") or ""),
                    "imported": False,
                    "idempotent": False,
                    "error": str(exc),
                }
            )

    return {
        "total": len(payload.records),
        "imported": imported,
        "existing": existing,
        "failed": failed,
        "auto_created_users": auto_created_users,
        "results": results,
    }


@public_router.get("/{token}", response_class=PlainTextResponse)
def migration_legacy_subscription(token: str, db: Session = Depends(get_db)):
    try:
        _, payload = legacy_payload(db, token)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    links = payload.get("links") or []
    body = "\n".join(str(item).strip() for item in links if str(item).strip())
    if not body:
        raise HTTPException(status_code=404, detail="preserved legacy links are unavailable")

    encoded = base64.b64encode(body.encode()).decode()
    return PlainTextResponse(encoded, media_type="text/plain; charset=utf-8")
