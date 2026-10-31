from __future__ import annotations

import re
import uuid
from typing import Any

from .models import ProtocolCredential, Subscription
from .routers import modern_account_delivery_v1


_runtime_applied = False
_original_provision_classic_protocol = None


def _uuid_from_items(raw: Any) -> str:
    """Recover the already-delivered V2Ray UUID from stored credential items."""
    if isinstance(raw, dict):
        items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        return ""

    for item in items:
        if not isinstance(item, dict):
            continue

        value = str(item.get("uuid") or "").strip()
        if value:
            try:
                return str(uuid.UUID(value))
            except ValueError:
                pass

        uri = str(item.get("uri") or "").strip()
        match = re.match(r"^vless://([^@/?#]+)@", uri)
        if match:
            try:
                return str(uuid.UUID(match.group(1)))
            except ValueError:
                pass

    return ""


def _deterministic_v2ray_uuid(subscription_id: int) -> str:
    """Stable fallback identity for a subscription before DB delivery exists."""
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"twinpanel:subscription:{int(subscription_id)}:v2ray",
        )
    )


def _existing_v2ray_uuid(ad: Any, db: Any, sub: Subscription) -> str:
    cred = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == sub.id,
            ProtocolCredential.protocol == "v2ray",
        )
        .first()
    )
    if cred is None:
        return ""

    return _uuid_from_items(ad._dec(cred.config_text_encrypted))


def install() -> None:
    """Make V2Ray account provisioning idempotent across HTTP retries.

    Subscription creation commits the subscription row before remote account
    provisioning. If a request reaches Xray but later fails during quota sync or
    response completion, a retry must reuse the same UUID instead of creating a
    second identity for the same subscription email.
    """

    global _runtime_applied, _original_provision_classic_protocol

    if _runtime_applied:
        return

    original = modern_account_delivery_v1._provision_classic_protocol
    _original_provision_classic_protocol = original

    async def _provision_classic_protocol_idempotent(
        ad: Any,
        db: Any,
        sub: Subscription,
        user: Any,
        protocol: str,
        nodes: list[Any],
        username: str,
        password: str,
        xray_id: str,
    ):
        if str(protocol or "").strip().lower() == "v2ray":
            existing = _existing_v2ray_uuid(ad, db, sub)
            xray_id = existing or _deterministic_v2ray_uuid(sub.id)

        return await original(
            ad,
            db,
            sub,
            user,
            protocol,
            nodes,
            username,
            password,
            xray_id,
        )

    modern_account_delivery_v1._provision_classic_protocol = (
        _provision_classic_protocol_idempotent
    )
    _runtime_applied = True

    print(
        "TWINPANEL_V2RAY_PROVISION_IDEMPOTENCY_V1_ACTIVE",
        flush=True,
    )
