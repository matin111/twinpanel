from __future__ import annotations

import re
import uuid
from typing import Any

from . import xray_modern_runtime


_runtime_applied = False
_original_merge_clients_script = None
_original_xray_account_modern = None


def _normalize_uuid(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError, AttributeError):
        return ""


def _uuid_from_item(item: Any) -> str:
    if not isinstance(item, dict):
        return ""

    direct = _normalize_uuid(item.get("uuid"))
    if direct:
        return direct

    uri = str(item.get("uri") or "").strip()
    match = re.match(r"^vless://([^@/?#]+)@", uri)
    return _normalize_uuid(match.group(1)) if match else ""


def _stored_xray_uuid(db: Any, subscription_id: int) -> tuple[str, Any]:
    """Return the durable V2Ray UUID already owned by this subscription.

    Successful historical credentials store the UUID in config_text_encrypted.
    A retry that died after the remote mutation but before the normal provisioner
    commit stores a small pending UUID marker in secret_encrypted instead.
    """

    from .models import ProtocolCredential
    from .routers import account_delivery as ad

    cred = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == int(subscription_id),
            ProtocolCredential.protocol == "v2ray",
        )
        .first()
    )

    if cred is None:
        return "", None

    decoded_items = ad._dec(cred.config_text_encrypted)
    if isinstance(decoded_items, dict):
        decoded_items = [decoded_items]
    if isinstance(decoded_items, list):
        for item in decoded_items:
            existing = _uuid_from_item(item)
            if existing:
                return existing, cred

    decoded_secret = ad._dec(cred.secret_encrypted)
    if isinstance(decoded_secret, dict):
        existing = _normalize_uuid(decoded_secret.get("uuid"))
        if existing:
            return existing, cred

    return "", cred


def _persist_pending_xray_uuid(
    db: Any,
    subscription_id: int,
    requested_uuid: str,
) -> str:
    """Make the Xray identity crash/retry safe before touching the remote node."""

    from .models import ProtocolCredential
    from .routers import account_delivery as ad

    existing, cred = _stored_xray_uuid(db, subscription_id)
    if existing:
        return existing

    stable_uuid = _normalize_uuid(requested_uuid) or str(uuid.uuid4())

    if cred is None:
        cred = ProtocolCredential(
            subscription_id=int(subscription_id),
            protocol="v2ray",
            is_active=False,
        )
        db.add(cred)
        db.flush()

    # admin-create-v2 already persists the subscription before provisioning.
    # Commit this authentication identity before the SSH/Xray mutation so a
    # timeout, worker restart, or HTTP retry cannot generate a second UUID for
    # the same mv-<subscription_id>@twinpanel email.
    cred.secret_encrypted = ad._enc(
        {
            "uuid": stable_uuid,
            "state": "pending_remote_provision",
        }
    )
    db.commit()
    return stable_uuid


def install() -> None:
    """Heal legacy duplicate-email drift and make Xray retries idempotent.

    Older account mutation updated only the first VLESS inbound. A retry could
    therefore leave the same subscription email mapped to different UUIDs across
    the remaining modern inbounds. The modern bootstrap must normalize that
    historical drift before its authoritative client-sync step can replace the
    identity on every inbound.

    Account provisioning also historically generated a fresh UUID on every
    attempt. Persisting the first requested UUID before the remote mutation makes
    a failed/timed-out request safe to retry instead of creating a second Xray
    identity while the UI is still waiting for the original HTTP response.
    """

    global _runtime_applied
    global _original_merge_clients_script
    global _original_xray_account_modern

    if _runtime_applied:
        return

    original_merge = xray_modern_runtime._merge_clients_script
    original_xray = xray_modern_runtime._xray_account_modern
    _original_merge_clients_script = original_merge
    _original_xray_account_modern = original_xray

    def _merge_clients_script_repair() -> str:
        script = original_merge()
        needle = 'raise RuntimeError("Xray duplicate email conflict")'

        # Preserve the first valid identity for a duplicated email and ignore
        # later conflicting copies. _client_sync_script() immediately follows
        # bootstrap and rewrites the requested email to one UUID on every VLESS
        # inbound. Keep this compatibility wrapper tolerant once the core merge
        # implementation eventually carries the same repair natively.
        if needle in script:
            script = script.replace(needle, "continue", 1)
        return script

    async def _xray_account_modern_idempotent(
        db: Any,
        node: Any,
        sub: Any,
        user: Any,
        client_id: str,
    ) -> dict[str, Any]:
        stable_id = _persist_pending_xray_uuid(
            db,
            int(sub.id),
            client_id,
        )
        return await original_xray(
            db,
            node,
            sub,
            user,
            stable_id,
        )

    xray_modern_runtime._merge_clients_script = _merge_clients_script_repair
    xray_modern_runtime._xray_account_modern = _xray_account_modern_idempotent
    _runtime_applied = True
    print(
        "TWINPANEL_XRAY_DUPLICATE_EMAIL_REPAIR_V1_ACTIVE "
        "stable_retry_uuid=1",
        flush=True,
    )
