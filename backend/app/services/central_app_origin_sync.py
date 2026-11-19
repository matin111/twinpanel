"""Best-effort, license-authenticated TwinConnect API-origin synchronization.

Never mutate the panel's domains, licenses, subscriptions or VPN profiles.
The vendor verifies the new HTTPS endpoint before switching its directory.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from ..central_app_identity import (
    central_app_entitled, installation_namespace, save_app_directory_alias,
)
from ..services.public_urls import _domain_origin
from ..domain_models import DomainType
from ..system_release import _vendor_post, ensure_installation_id, load_license_state

_SYNC_STATE_FILE = Path(os.getenv(
    "TWINCONNECT_ORIGIN_SYNC_STATE_FILE",
    "/var/lib/twinpanel-license/app-origin-sync.json",
))


def _last_synced() -> dict:
    try:
        value = json.loads(_SYNC_STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_synced(installation_id: str, origin: str, grant_digest: str) -> None:
    path = _SYNC_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps({
        "installation_id": installation_id,
        "api_origin": origin,
        "grant_digest": grant_digest,
    }), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)


def sync_app_origin(db: Session, *, force: bool = False) -> dict:
    if not central_app_entitled():
        return {"status": "not_entitled"}
    # Only a managed API domain is authoritative for an automatic cutover.
    # Never overwrite a manually registered origin with a generic fallback.
    managed = _domain_origin(db, DomainType.API)
    if not managed:
        return {"status": "no_managed_api_domain"}
    origin = str(managed).strip().rstrip("/")
    parsed = urlsplit(origin)
    # A domain undergoing ACME/SSL issuance must never replace the old URL.
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.path not in ("", "/") or parsed.port not in (None, 443)):
        return {"status": "waiting_for_https"}
    installation_id = ensure_installation_id()
    state = load_license_state()
    grant = str(state.get("signed_entitlement") or "").strip()
    if not grant:
        return {"status": "no_signed_entitlement"}
    grant_digest = hashlib.sha256(grant.encode("utf-8")).hexdigest()[:20]
    previous = _last_synced()
    if (not force and previous.get("installation_id") == installation_id
            and previous.get("api_origin") == origin
            and previous.get("grant_digest") == grant_digest):
        return {"status": "unchanged"}
    payload = {
        "installation_id": installation_id,
        "signed_entitlement": grant,
        "api_origin": origin,
    }
    try:
        result = _vendor_post("/v1/app/origin/sync", payload)
    except httpx.HTTPStatusError as exc:
        # The first app license may have no directory yet. Create it only
        # through the signed registration route with the same HTTPS proof.
        if exc.response.status_code != 404:
            raise
        result = _vendor_post("/v1/app/register", payload)
    namespace = installation_namespace(installation_id)
    if result.get("namespace") != namespace:
        raise ValueError("VENDOR_NAMESPACE_MISMATCH")
    alias = result.get("short_namespace") or namespace
    save_app_directory_alias(installation_id, alias)
    # Success is persisted *only after* vendor confirmation. On failure,
    # the previous vendor URL and this checkpoint remain unchanged.
    _save_synced(installation_id, origin, grant_digest)
    return {"status": "synced", "api_origin": result.get("api_origin")}


def sync_app_origin_safely(db: Session, *, force: bool = False) -> dict:
    try:
        return sync_app_origin(db, force=force)
    except Exception as exc:
        return {"status": "pending", "reason": type(exc).__name__}


def sync_app_origin_background() -> None:
    # HTTP request sessions are already closed when background tasks run.
    from ..database import SessionLocal
    with SessionLocal() as db:
        sync_app_origin_safely(db)
