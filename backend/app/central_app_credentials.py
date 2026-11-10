"""Issue/verify app-only credentials; never change a VPN account password.

A reissue explicitly rotates just the app password and invalidates app
sessions. The subscription share URL and all protocol credentials remain stable.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from functools import lru_cache
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .central_app_credential_models import SubscriptionAppCredential
from .central_app_identity import (
    central_app_entitled, installation_namespace, reseller_prefix,
)
from .config import settings
from .models import Subscription
from .models_reseller import Reseller, ResellerSubscription
from .security import hash_password, verify_password
from .system_release import ensure_installation_id

_APP_PURPOSE = "twinconnect-session-v1"
_BAD_LOGIN = "APP_LOGIN_INVALID"
@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    # Delay bcrypt initialization until an unknown account is actually tried.
    return hash_password("twinconnect-nonexistent-account")


def _fernet() -> Fernet:
    material = hashlib.sha256(
        b"twinpanel:app-password-delivery:v1:" + settings.app_secret_key.encode("utf-8")
    ).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def _current_reseller_id(db: Session, sub_id: int) -> int:
    link = db.query(ResellerSubscription).filter(
        ResellerSubscription.subscription_id == int(sub_id)
    ).first()
    return int(link.reseller_id) if link else 0


def _check_app_entitlement() -> None:
    if not central_app_entitled():
        raise HTTPException(status_code=403, detail="CENTRAL_APP_NOT_INCLUDED")


def _active_subscription(db: Session, sub_id: int) -> Subscription:
    _check_app_entitlement()
    sub = db.get(Subscription, int(sub_id))
    if sub is None:
        raise HTTPException(status_code=401, detail=_BAD_LOGIN)
    status = str(getattr(sub.status, "value", sub.status) or "").lower()
    if status != "active" or (sub.expires_at and sub.expires_at <= datetime.utcnow()):
        raise HTTPException(status_code=403, detail="APP_SUBSCRIPTION_INACTIVE")
    owner = _current_reseller_id(db, sub.id)
    if owner:
        reseller = db.get(Reseller, owner)
        if reseller is None or not reseller.is_active:
            raise HTTPException(status_code=403, detail="APP_OWNER_INACTIVE")
    return sub


def _username(reseller_id: int) -> str:
    installation = ensure_installation_id()
    prefix = (reseller_prefix(installation, reseller_id)
              if reseller_id > 0
              else installation_namespace(installation) + "_A_")
    return prefix + "APP" + secrets.token_hex(8).upper()


def _password() -> str:
    # High entropy, all ASCII, printable; intentionally distinct from VPN password.
    return secrets.token_urlsafe(20)


def get_or_issue_app_credentials(
    db: Session, sub: Subscription, *, reseller_id: int | None = None,
) -> SubscriptionAppCredential | None:
    """Idempotent issuance. Caller commits with the subscription transaction.

    For historical subscriptions, the ownership is derived from its existing
    link. No account is issued on public/unauthenticated retrieval.
    """
    if not central_app_entitled():
        return None
    owner = int(reseller_id) if reseller_id is not None else _current_reseller_id(db, sub.id)
    if owner < 0:
        raise ValueError("invalid_app_owner")
    # Serialize concurrent first-issue requests for historical subscriptions.
    db.query(Subscription.id).filter(Subscription.id == int(sub.id)).with_for_update().first()
    row = db.get(SubscriptionAppCredential, int(sub.id))
    if row:
        if int(row.reseller_id) != owner:
            raise HTTPException(status_code=409, detail="APP_OWNER_MISMATCH")
        return row
    username = _username(owner)
    password = _password()
    row = SubscriptionAppCredential(
        subscription_id=int(sub.id),
        reseller_id=owner,
        app_username=username,
        password_hash=hash_password(password),
        delivery_password_encrypted=_fernet().encrypt(password.encode("utf-8")).decode("ascii"),
        revision=1,
    )
    db.add(row)
    db.flush()
    return row


def app_delivery_payload(db: Session, sub: Subscription) -> dict | None:
    """Requires prior authenticated owner check by caller."""
    if not central_app_entitled():
        return None
    owner = _current_reseller_id(db, sub.id)
    row = get_or_issue_app_credentials(db, sub, reseller_id=owner)
    if row is None:
        return None
    try:
        password = _fernet().decrypt(
            row.delivery_password_encrypted.encode("ascii")
        ).decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="APP_SECRET_UNREADABLE") from exc
    return {
        "username": row.app_username,
        "password": password,
        "revision": row.revision,
    }


def rotate_app_credentials(db: Session, sub: Subscription) -> dict | None:
    """Explicit authenticated action only. VPN username/password untouched."""
    current = app_delivery_payload(db, sub)
    if current is None:
        return None
    row = db.get(SubscriptionAppCredential, int(sub.id))
    password = _password()
    row.password_hash = hash_password(password)
    row.delivery_password_encrypted = _fernet().encrypt(
        password.encode("utf-8")
    ).decode("ascii")
    row.revision += 1
    row.failed_attempts = 0
    row.locked_until = None
    db.flush()
    return {"username": row.app_username, "password": password, "revision": row.revision}


def authenticate_app(db: Session, username: str, password: str) -> tuple[Subscription, str]:
    """Lockout is stored in DB, not only a single API process's memory."""
    _check_app_entitlement()
    if len(username) > 120 or len(password) > 256:
        raise HTTPException(status_code=401, detail=_BAD_LOGIN)
    row = db.query(SubscriptionAppCredential).filter(
        SubscriptionAppCredential.app_username == username.strip()
    ).with_for_update().first()
    if row is None:
        verify_password(password[:72], _dummy_hash())
        raise HTTPException(status_code=401, detail=_BAD_LOGIN)
    now = datetime.utcnow()
    if row.locked_until and row.locked_until > now:
        raise HTTPException(status_code=429, detail="APP_LOGIN_LOCKED")
    if not verify_password(password, row.password_hash):
        row.failed_attempts = int(row.failed_attempts or 0) + 1
        if row.failed_attempts >= 5:
            row.locked_until = now + timedelta(minutes=15)
            row.failed_attempts = 0
        db.commit()
        raise HTTPException(status_code=401, detail=_BAD_LOGIN)
    sub = _active_subscription(db, row.subscription_id)
    actual_owner = _current_reseller_id(db, sub.id)
    if int(row.reseller_id) != actual_owner:
        raise HTTPException(status_code=403, detail="APP_OWNER_MISMATCH")
    row.failed_attempts = 0
    row.locked_until = None
    db.commit()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
    scope = installation_namespace(ensure_installation_id())
    session = jwt.encode({
        "purpose": _APP_PURPOSE,
        "sid": int(sub.id),
        "revision": int(row.revision),
        "namespace": scope,
        "exp": expiry,
    }, settings.app_secret_key, algorithm="HS256")
    return sub, session


def verify_app_session(db: Session, token: str) -> Subscription:
    _check_app_entitlement()
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        if (payload.get("purpose") != _APP_PURPOSE
                or payload.get("namespace") != installation_namespace(ensure_installation_id())):
            raise ValueError("invalid_session_scope")
        sid = int(payload["sid"])
        revision = int(payload["revision"])
    except (JWTError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="APP_SESSION_INVALID") from None
    row = db.get(SubscriptionAppCredential, sid)
    if row is None or int(row.revision) != revision:
        raise HTTPException(status_code=401, detail="APP_SESSION_REVOKED")
    sub = _active_subscription(db, sid)
    if int(row.reseller_id) != _current_reseller_id(db, sid):
        raise HTTPException(status_code=401, detail="APP_OWNER_CHANGED")
    return sub
