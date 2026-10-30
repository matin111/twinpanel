from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from ..config import settings
from ..migration_import_models import MigrationImportRecord
from ..models import Subscription, SubscriptionProtocol, SubscriptionStatus, User
from ..protocol_account_registry import normalize_protocols
from .migration_center_v1 import SUPPORTED_SOURCES, normalize_record


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.app_secret_key.encode()).digest())
    return Fernet(key)


def _enc_payload(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False).encode()
    return _fernet().encrypt(raw).decode()


def _dec_payload(value: str) -> Any:
    try:
        return json.loads(_fernet().decrypt(value.encode()).decode())
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return None


def _legacy_token(url: str | None) -> str | None:
    raw = str(url or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
        path = (parsed.path or "").rstrip("/")
        token = path.rsplit("/", 1)[-1].strip() if path else ""
    except Exception:
        return None
    return token or None


def _links_from_normalized(row: dict[str, Any]) -> list[str]:
    credentials = row.get("credentials") or {}
    values = credentials.get("links")
    if isinstance(values, list):
        return [str(item).strip() for item in values if str(item).strip()]
    for key in ("config", "config_text"):
        value = credentials.get(key)
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def import_record(
    db: Session,
    *,
    source: str,
    record: dict[str, Any],
    target_user_id: int,
    protocols: list[str],
    traffic_limit_bytes: int = 0,
    traffic_used_bytes: int = 0,
    starts_at: datetime | None = None,
    expires_at: datetime | None = None,
    activation_duration_days: int | None = None,
    allow_inactive_target: bool = False,
) -> dict[str, Any]:
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported migration source: {source}")

    normalized = normalize_record(source, record, 0)
    source_id = str(normalized.get("source_id") or "").strip()
    if not source_id:
        raise ValueError("source_id is required for idempotent import")
    if not normalized.get("username"):
        raise ValueError("username is required for import")

    links = _links_from_normalized(normalized)
    if not links and not normalized.get("credentials"):
        raise ValueError("existing credential material is required")

    existing = (
        db.query(MigrationImportRecord)
        .filter(
            MigrationImportRecord.source == source,
            MigrationImportRecord.source_id == source_id,
        )
        .first()
    )
    if existing:
        return {
            "imported": False,
            "idempotent": True,
            "subscription_id": existing.subscription_id,
            "migration_record_id": existing.id,
            "legacy_url": existing.legacy_url,
            "legacy_token": existing.legacy_token,
        }

    user = db.get(User, target_user_id)
    if not user or (not user.is_active and not allow_inactive_target):
        raise ValueError("target TwinPanel user is missing or inactive")

    requested_protocols = protocols or ["v2ray"]
    try:
        protocol_values = normalize_protocols(requested_protocols)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if not protocol_values:
        protocol_values = ["v2ray"]

    legacy_url = normalized.get("legacy_subscription_url")
    token = _legacy_token(legacy_url)

    if token:
        marker_collision = (
            db.query(MigrationImportRecord)
            .filter(MigrationImportRecord.legacy_token == token)
            .first()
        )
        if marker_collision:
            raise ValueError("legacy subscription token is already imported")

    share_code = None
    if token and len(token) <= 64:
        collision = db.query(Subscription).filter(Subscription.share_code == token).first()
        if collision is None:
            share_code = token

    sub = Subscription(
        user_id=user.id,
        plan_id=None,
        status=SubscriptionStatus.ACTIVE,
        starts_at=starts_at,
        expires_at=expires_at,
        activation_duration_days=activation_duration_days,
        traffic_limit_bytes=max(0, int(traffic_limit_bytes or 0)),
        traffic_used_bytes=max(0, int(traffic_used_bytes or 0)),
        account_username=str(normalized["username"]),
        account_password_encrypted=(
            str((normalized.get("credentials") or {}).get("password") or "").strip() or None
        ),
        share_code=share_code,
    )
    db.add(sub)
    db.flush()

    for protocol in protocol_values:
        db.add(SubscriptionProtocol(subscription_id=sub.id, protocol=protocol))

    preserved = {
        "normalized": normalized,
        "links": links,
        "protocols": protocol_values,
        "legacy_delivery": {
            "token": token,
            "share_code_bound": bool(share_code),
            "reverse_proxy_required": bool(legacy_url),
        },
    }
    marker = MigrationImportRecord(
        source=source,
        source_id=source_id,
        subscription_id=sub.id,
        legacy_url=legacy_url,
        legacy_token=token,
        preserved_payload_encrypted=_enc_payload(preserved),
        status="imported",
    )
    db.add(marker)
    db.commit()
    db.refresh(marker)

    return {
        "imported": True,
        "idempotent": False,
        "subscription_id": sub.id,
        "migration_record_id": marker.id,
        "legacy_url": legacy_url,
        "legacy_token": token,
        "share_code_bound": bool(share_code),
        "legacy_passthrough_path": f"/v1/migration/legacy/{token}" if token else None,
        "reverse_proxy_required": bool(legacy_url),
    }


def legacy_payload(db: Session, token: str) -> tuple[Subscription, dict[str, Any]]:
    marker = (
        db.query(MigrationImportRecord)
        .filter(MigrationImportRecord.legacy_token == str(token or "").strip())
        .first()
    )
    if not marker or marker.status != "imported":
        raise LookupError("legacy migration token not found")

    sub = db.get(Subscription, marker.subscription_id)
    if not sub:
        raise LookupError("imported subscription not found")
    if getattr(sub.status, "value", str(sub.status)) != "active":
        raise PermissionError("subscription is not active")
    if sub.expires_at and sub.expires_at <= datetime.utcnow():
        raise PermissionError("subscription is expired")

    payload = _dec_payload(marker.preserved_payload_encrypted)
    if not isinstance(payload, dict):
        raise LookupError("preserved migration payload is unavailable")
    return sub, payload
