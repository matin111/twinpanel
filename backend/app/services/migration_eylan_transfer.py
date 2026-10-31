from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..migration_import_models import MigrationImportRecord
from ..models import Subscription, SubscriptionStatus
from .migration_eylan import EYLAN_SOURCE, duration_days_for_expiry
from .migration_import_v2 import _enc_payload
from .migration_v2ray_batch import provision_migrated_v2ray_batch
from .subscription_factory import create_subscription_core


EYLAN_STAGE_LIMIT = 100


def _naive_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=None)


def stage_eylan_records(
    db: Session,
    *,
    records: list[Any],
    target_user_id: int,
) -> dict[str, Any]:
    """Create/update Eylan subscriptions without touching remote Xray nodes.

    The UI intentionally calls this in small chunks. Each request remains short,
    while migration markers keep the operation idempotent if the browser or
    reverse proxy disconnects between chunks.
    """

    if len(records) > EYLAN_STAGE_LIMIT:
        raise ValueError(f"Eylan stage accepts at most {EYLAN_STAGE_LIMIT} records per request")

    source_ids = [str(record.source_id).strip() for record in records]
    existing_markers = (
        db.query(MigrationImportRecord)
        .filter(
            MigrationImportRecord.source == EYLAN_SOURCE,
            MigrationImportRecord.source_id.in_(source_ids),
        )
        .all()
        if source_ids
        else []
    )
    markers_by_source = {str(item.source_id): item for item in existing_markers}

    imported = 0
    existing = 0
    already_imported = 0
    staged_source_ids: list[str] = []
    items: list[dict[str, Any]] = []

    for record in records:
        source_id = str(record.source_id).strip()
        marker = markers_by_source.get(source_id)

        if marker is not None:
            sub = db.get(Subscription, marker.subscription_id)
            if sub is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Eylan marker {source_id} points to a missing subscription",
                )
            if int(sub.user_id) != int(target_user_id):
                raise HTTPException(
                    status_code=409,
                    detail=f"Eylan account {source_id} belongs to another TwinPanel user",
                )
            sub.account_username = record.username.strip()
            sub.account_password_encrypted = record.password.strip()
            sub.traffic_limit_bytes = int(record.traffic_limit_bytes)
            sub.traffic_used_bytes = int(record.traffic_used_bytes)
            sub.expires_at = _naive_datetime(record.expires_at)
            sub.activation_duration_days = None
            existing += 1

            if marker.status == "imported":
                already_imported += 1
                items.append(
                    {
                        "source_id": source_id,
                        "subscription_id": sub.id,
                        "existing": True,
                        "already_imported": True,
                    }
                )
                continue
        else:
            sub = create_subscription_core(
                db=db,
                user_id=target_user_id,
                plan_id=None,
                traffic_bytes=int(record.traffic_limit_bytes),
                duration_days=duration_days_for_expiry(record.expires_at),
                node_ids=[],
                protocols=["v2ray"],
                username=record.username.strip(),
                password=record.password.strip(),
            )
            sub.traffic_used_bytes = int(record.traffic_used_bytes)
            sub.expires_at = _naive_datetime(record.expires_at)
            sub.activation_duration_days = None
            marker = MigrationImportRecord(
                source=EYLAN_SOURCE,
                source_id=source_id,
                subscription_id=sub.id,
                legacy_url=None,
                legacy_token=None,
                preserved_payload_encrypted=_enc_payload(
                    {
                        "source": EYLAN_SOURCE,
                        "source_id": source_id,
                        "username": record.username.strip(),
                        "traffic_limit_bytes": int(record.traffic_limit_bytes),
                        "traffic_used_bytes": int(record.traffic_used_bytes),
                        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                        "credential_policy": "twinpanel_generated_protocol_credentials",
                    }
                ),
                status="staged",
            )
            db.add(marker)
            db.flush()
            markers_by_source[source_id] = marker
            imported += 1

        marker.status = "staged"
        staged_source_ids.append(source_id)
        items.append(
            {
                "source_id": source_id,
                "subscription_id": sub.id,
                "existing": marker.subscription_id != sub.id or source_id in markers_by_source,
                "already_imported": False,
            }
        )

    db.commit()
    return {
        "ok": True,
        "source": EYLAN_SOURCE,
        "imported": imported,
        "existing": existing,
        "already_imported": already_imported,
        "staged": len(staged_source_ids),
        "staged_source_ids": staged_source_ids,
        "items": items,
    }


async def finalize_eylan_records(
    db: Session,
    *,
    source_ids: list[str],
    target_user_id: int,
) -> dict[str, Any]:
    """Provision all staged Eylan subscriptions in one V2Ray node transaction."""

    normalized = sorted({str(item).strip() for item in source_ids if str(item).strip()})
    if not normalized:
        return {
            "ok": True,
            "source": EYLAN_SOURCE,
            "subscriptions": 0,
            "existing_imported": 0,
            "provision": {
                "ok": True,
                "subscriptions": 0,
                "nodes": 0,
                "node_restarts": 0,
                "errors": [],
            },
        }

    markers = (
        db.query(MigrationImportRecord)
        .filter(
            MigrationImportRecord.source == EYLAN_SOURCE,
            MigrationImportRecord.source_id.in_(normalized),
        )
        .all()
    )
    markers_by_source = {str(item.source_id): item for item in markers}
    missing = [item for item in normalized if item not in markers_by_source]
    if missing:
        raise HTTPException(
            status_code=409,
            detail="Eylan finalize is missing staged records: " + ",".join(missing[:20]),
        )

    subscription_ids = sorted({int(item.subscription_id) for item in markers})
    subscriptions = (
        db.query(Subscription)
        .filter(Subscription.id.in_(subscription_ids))
        .all()
    )
    subscriptions_by_id = {int(item.id): item for item in subscriptions}

    subscription_uuids: dict[int, str] = {}
    marker_ids: list[int] = []
    existing_imported = 0

    for source_id in normalized:
        marker = markers_by_source[source_id]
        sub = subscriptions_by_id.get(int(marker.subscription_id))
        if sub is None:
            raise HTTPException(
                status_code=409,
                detail=f"Eylan marker {source_id} points to a missing subscription",
            )
        if int(sub.user_id) != int(target_user_id):
            raise HTTPException(
                status_code=409,
                detail=f"Eylan account {source_id} belongs to another TwinPanel user",
            )
        if marker.status == "imported":
            existing_imported += 1
            continue
        marker.status = "provisioning"
        marker_ids.append(int(marker.id))
        subscription_uuids[int(sub.id)] = str(uuid.uuid4())

    db.commit()

    if not subscription_uuids:
        return {
            "ok": True,
            "source": EYLAN_SOURCE,
            "subscriptions": 0,
            "existing_imported": existing_imported,
            "provision": {
                "ok": True,
                "subscriptions": 0,
                "nodes": 0,
                "node_restarts": 0,
                "errors": [],
            },
        }

    try:
        provision = await provision_migrated_v2ray_batch(db, subscription_uuids)
    except Exception:
        for marker_id in marker_ids:
            marker = db.get(MigrationImportRecord, marker_id)
            if marker is not None:
                marker.status = "failed"
        for subscription_id in subscription_uuids:
            sub = db.get(Subscription, subscription_id)
            if sub is not None:
                sub.status = SubscriptionStatus.SUSPENDED
        db.commit()
        raise

    final_status = "imported" if int(provision.get("nodes") or 0) > 0 else "failed"
    for marker_id in marker_ids:
        marker = db.get(MigrationImportRecord, marker_id)
        if marker is not None:
            marker.status = final_status
    for subscription_id in subscription_uuids:
        sub = db.get(Subscription, subscription_id)
        if sub is not None:
            sub.status = (
                SubscriptionStatus.ACTIVE
                if final_status == "imported"
                else SubscriptionStatus.SUSPENDED
            )
    db.commit()

    return {
        "ok": bool(provision.get("ok", True)),
        "source": EYLAN_SOURCE,
        "subscriptions": len(subscription_uuids),
        "existing_imported": existing_imported,
        "provision": provision,
    }
