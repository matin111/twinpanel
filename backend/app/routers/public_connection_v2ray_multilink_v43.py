from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from . import public_connection_all_multilink_v34 as multilink


MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_V43"
FAST_MARKER = "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_SINGLE_PAYLOAD_V50"
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

    # V50 latency fix:
    # multilink._active() already resolves the customer payload through the
    # runtime-patched account_delivery._stored_info chain. V30/V47 therefore
    # enforce the final customer-safe Xray profile policy before this function
    # receives the payload. Rebuilding the payload a second time through
    # xray_public_delivery_runtime duplicated all delivery work and, critically,
    # regenerated expensive QR SVGs for every Xray profile. Under live API load
    # that duplicate CPU/GIL work pushed a standard subscription fetch to
    # roughly 9-12 seconds and caused Hiddify imports to time out.
    #
    # Reuse the single payload returned by _active(). This keeps the exact same
    # customer policy, active-subscription guard, Mother/explicit delivery
    # wrappers and real per-profile URIs while eliminating the duplicate pass.
    sub, payload = multilink._active(token, db)
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
    setattr(multilink, "_V2RAY_MULTILINK_SINGLE_PAYLOAD_V50", FAST_MARKER)
    _applied = True


__all__ = [
    "MARKER",
    "FAST_MARKER",
    "apply_v2ray_multilink_v43",
]
