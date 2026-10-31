from __future__ import annotations

import base64
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..migration_import_models import MigrationImportRecord
from ..models import Subscription
from ..services.migration_import_v2 import import_record, legacy_payload
from ..services.migration_v2ray_batch import provision_migrated_v2ray_batch


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
    traffic_limit_bytes: int | None = Field(default=None, ge=0)
    traffic_used_bytes: int | None = Field(default=None, ge=0)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    activation_duration_days: int | None = Field(default=None, ge=1, le=3650)


class MigrationBatchImportIn(BaseModel):
    source: MigrationSource
    records: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    target_user_id: int
    protocols: list[str] = Field(default_factory=lambda: ["v2ray"], max_length=20)


def _preserved_v2ray_uuid(record: dict[str, Any]) -> str:
    credentials = record.get("credentials")
    if not isinstance(credentials, dict):
        raise ValueError("V2Ray migration record is missing preserved credentials")
    raw = str(credentials.get("uuid") or "").strip()
    if not raw:
        raise ValueError("V2Ray migration record is missing preserved UUID")
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"invalid preserved V2Ray UUID: {raw}") from exc


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
async def migration_import_batch(
    payload: MigrationBatchImportIn,
    db: Session = Depends(get_db),
):
    """Import and provision a V2Ray migration batch without per-account restarts.

    The normal single-account endpoint remains unchanged for compatibility. This
    optimized path is deliberately limited to V2Ray because its canonical
    account driver rewrites Xray config.json and restarts the service. Applying
    all imported clients in one node transaction is both faster and race-free.
    """

    protocols = [str(item).strip().lower() for item in payload.protocols if str(item).strip()]
    if protocols != ["v2ray"]:
        raise HTTPException(
            status_code=422,
            detail="Bulk migration provisioning currently supports exactly the v2ray protocol",
        )

    try:
        # Validate the complete batch before the first database write so a bad
        # source UUID cannot leave a half-imported batch behind.
        preserved_uuids = [_preserved_v2ray_uuid(record) for record in payload.records]

        imported = 0
        existing = 0
        subscription_uuids: dict[int, str] = {}
        results: list[dict[str, Any]] = []

        for record, preserved_uuid in zip(payload.records, preserved_uuids, strict=True):
            result = import_record(
                db,
                source=payload.source,
                record=record,
                target_user_id=payload.target_user_id,
                protocols=["v2ray"],
            )
            subscription_id = int(result["subscription_id"])
            subscription_uuids[subscription_id] = preserved_uuid
            results.append(result)
            if result.get("imported"):
                imported += 1
            elif result.get("idempotent"):
                existing += 1

        provision = await provision_migrated_v2ray_batch(db, subscription_uuids)

        return {
            "ok": bool(provision.get("ok")),
            "imported": imported,
            "existing": existing,
            "subscriptions": len(subscription_uuids),
            "provision": provision,
            "items": results,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"migration batch imported but node provisioning failed: {exc}",
        ) from exc


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
