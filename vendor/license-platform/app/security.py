from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from jose import JWTError, jwt

from .settings import settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_license_key(value: str) -> str:
    material = f"{settings.license_key_pepper}|{str(value or '').strip().upper()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def generate_license_key() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    groups = []
    for _ in range(4):
        groups.append("".join(secrets.choice(alphabet) for _ in range(5)))
    return "TP-" + "-".join(groups)


@lru_cache(maxsize=1)
def private_key() -> str:
    return settings.signing_private_key_file.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def public_key() -> str:
    return settings.signing_public_key_file.read_text(encoding="utf-8")


def sign_entitlement(claims: dict, ttl_seconds: int | None = None) -> str:
    now = utc_now()
    ttl = int(ttl_seconds or settings.entitlement_ttl_seconds)
    payload = {
        **claims,
        "iss": settings.issuer,
        "aud": settings.audience,
        "iat": int(now.timestamp()),
        "nbf": int((now - timedelta(seconds=5)).timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, private_key(), algorithm="RS256")


def verify_entitlement(token: str) -> dict:
    try:
        value = jwt.decode(
            token,
            public_key(),
            algorithms=["RS256"],
            audience=settings.audience,
            issuer=settings.issuer,
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise ValueError("INVALID_SIGNED_ENTITLEMENT") from exc
    if not isinstance(value, dict):
        raise ValueError("INVALID_SIGNED_ENTITLEMENT")
    return value


def sign_download_token(*, installation_id: str, version: str) -> str:
    return sign_entitlement(
        {
            "scope": "release_download",
            "installation_id": installation_id,
            "version": version,
        },
        ttl_seconds=settings.download_token_ttl_seconds,
    )


def verify_download_token(token: str, *, installation_id: str | None = None, version: str | None = None) -> dict:
    value = verify_entitlement(token)
    if value.get("scope") != "release_download":
        raise ValueError("INVALID_DOWNLOAD_SCOPE")
    if installation_id and value.get("installation_id") != installation_id:
        raise ValueError("DOWNLOAD_INSTALLATION_MISMATCH")
    if version and value.get("version") != version:
        raise ValueError("DOWNLOAD_VERSION_MISMATCH")
    return value


def verify_admin_token(value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(str(value), settings.admin_token)
