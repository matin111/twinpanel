from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from . import public_connection_all_multilink_v34 as multilink


MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_V43"
_applied = False
_original_all_share_uris = multilink._all_share_uris
_original_delivery = multilink._delivery


def _profile_uris(item: dict[str, Any]) -> list[str]:
    """Return every customer-safe Xray profile URI in runtime policy order."""

    from .. import xray_public_delivery_runtime as delivery

    rows: list[str] = []
    seen: set[str] = set()
    for profile in delivery._customer_profiles(item):
        uri = str(profile.get("uri") or "").strip()
        if "://" not in uri or uri in seen:
            continue
        seen.add(uri)
        rows.append(uri)
    return rows


def _all_share_uris_v43(
    sub: Any,
    protocol: str,
    items: list[dict[str, Any]],
) -> list[str]:
    protocol_key = multilink._normalize(protocol)
    if protocol_key != "v2ray":
        return _original_all_share_uris(sub, protocol, items)

    rows: list[str] = []
    seen: set[str] = set()

    for item in items:
        item_rows = _profile_uris(item)
        if not item_rows:
            legacy = multilink._share_uri(sub, "v2ray", item)
            item_rows = [legacy] if legacy else []

        if not item_rows:
            return []

        for uri in item_rows:
            if uri in seen:
                continue
            seen.add(uri)
            rows.append(uri)

    return rows


def _delivery_v43(token: str, protocol: str, db):
    protocol_key = multilink._normalize(protocol)
    if protocol_key != "v2ray":
        return _original_delivery(token, protocol, db)

    # V34 captured account_delivery._public_payload before the Xray runtime
    # adds the preserved TCP-simple fallback. Rebuild only the V2Ray delivery
    # from the runtime customer payload so every country/node contributes the
    # same customer-safe profile set used by the Public Connect page.
    from .. import xray_public_delivery_runtime as delivery

    sub, _legacy_payload = multilink._active(token, db)
    payload = delivery._public_payload_customer_xray(db, sub)
    items = multilink._protocol_items(payload, "v2ray")
    if not items:
        raise HTTPException(
            status_code=404,
            detail="سرور آماده‌ای برای این پروتکل وجود ندارد",
        )

    uris = _all_share_uris_v43(sub, "v2ray", items)
    if uris:
        # Keep metadata as real node/country count. The subscription payload
        # deliberately contains multiple URIs per node (normally 3).
        return "uri", len(items), sub, items, uris

    outbounds = multilink._all_outbounds("v2ray", items)
    if outbounds:
        return "singbox", len(items), sub, items, outbounds

    return "bundle", len(items), sub, items, None


def apply_v2ray_multilink_v43() -> None:
    global _applied
    if _applied:
        return

    multilink._all_share_uris = _all_share_uris_v43
    multilink._delivery = _delivery_v43
    setattr(multilink, "_V2RAY_MULTILINK_V43", MARKER)
    _applied = True


__all__ = [
    "MARKER",
    "apply_v2ray_multilink_v43",
]
