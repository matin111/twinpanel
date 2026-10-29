from __future__ import annotations

from typing import Any

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
    kind, count, sub, items, payload = _original_delivery(token, protocol, db)
    if multilink._normalize(protocol) == "v2ray" and kind == "uri":
        # Metadata keeps the real country/node count while payload contains
        # every customer-safe connection profile for every node.
        count = len(items)
    return kind, count, sub, items, payload


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
