from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote


# TWINPANEL_XRAY_PUBLIC_HUB_PROFILES_V48
#
# Public payload policy remains owned by the Xray runtime (V47+). This module
# only renders the real ordered profiles already present on one Xray delivery
# item. It deliberately does not invent, reconcile, reorder, or provision
# profiles, and it does not touch Multilink/Subscription delivery.

MARKER = "TWINPANEL_XRAY_PUBLIC_HUB_PROFILES_V48"


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _profile_title(profile: dict[str, Any], index: int) -> str:
    return str(
        profile.get("title")
        or profile.get("profile_title")
        or profile.get("name")
        or profile.get("id")
        or f"Xray Profile {index + 1}"
    ).strip()


def _profiles(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only real, usable profiles in the producer-provided order."""

    raw = item.get("profiles")
    if not isinstance(raw, list):
        return []

    result: list[dict[str, Any]] = []
    for value in raw:
        if not isinstance(value, dict):
            continue
        profile = dict(value)
        if not str(profile.get("uri") or "").strip():
            continue
        result.append(profile)
    return result


def _hiddify_link(uri: str, title: str) -> str:
    # Hiddify's current URL-scheme accepts a single proxy link as <sublink>.
    return f"hiddify://import/{quote(uri, safe='')}#{quote(title, safe='')}"


def _karing_link(uri: str, title: str) -> str:
    # Same direct-config URL scheme already used by TwinPanel Modern Import V15.
    return (
        "karing://install-config?url="
        f"{quote(uri, safe='')}&name={quote(title, safe='')}"
    )


def render_xray_quick_connect_profiles(item: dict[str, Any]) -> str | None:
    """Render the real per-server Xray profiles for non-Smart Quick Connect.

    None means the caller must preserve its historical single-link fallback.
    """

    profiles = _profiles(item)
    if not profiles:
        return None

    cards: list[str] = []
    for index, profile in enumerate(profiles):
        uri = str(profile.get("uri") or "").strip()
        title = _profile_title(profile, index)
        profile_id = str(profile.get("id") or "").strip()
        transport = str(profile.get("transport") or "").strip()
        security = str(profile.get("security") or "").strip()
        qr = str(profile.get("qr") or "").strip()

        qr_html = (
            f'<img class="qr" src="{_h(qr)}" alt="QR {_h(title)}">'
            if qr
            else ""
        )
        metadata = " · ".join(value for value in (transport, security) if value)
        subtitle = metadata or "V2Ray / Xray"
        hiddify = _hiddify_link(uri, title)
        karing = _karing_link(uri, title)

        cards.append(
            '<div class="action-row tp-v48-xray-profile" '
            f'data-tp-xray-profile-id="{_h(profile_id)}" '
            f'data-tp-xray-profile-title="{_h(title)}">'
            f'{qr_html}'
            '<div class="action-copy">'
            f'<b class="tp-v48-profile-title">{_h(title)}</b>'
            f'<small>{_h(subtitle)}</small>'
            '</div>'
            '<div class="action-buttons tp-v48-profile-actions">'
            f'<button class="copy-btn" type="button" data-copy="{_h(uri)}">کپی لینک</button>'
            f'<a class="primary-btn tp-v48-v2rayn" href="{_h(uri)}" rel="noopener noreferrer">v2rayN / Client</a>'
            f'<a class="primary-btn tp-v48-hiddify" href="{_h(hiddify)}" rel="noopener noreferrer">Hiddify</a>'
            f'<a class="primary-btn tp-v48-karing" href="{_h(karing)}" rel="noopener noreferrer">Karing</a>'
            '</div>'
            '</div>'
        )

    return (
        f'<div class="tp-v48-xray-profiles" data-tp-xray-profile-count="{len(cards)}">'
        + "".join(cards)
        + "</div>"
    )
