from __future__ import annotations

import base64
import io
from typing import Any

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from .. import xray_public_delivery_runtime as xray_delivery
from ..database import get_db
from .account_delivery import _public_payload, _subscription_from_share_token


router = APIRouter(tags=["public-connection-multilink-v7"])


# TWINPANEL_PUBLIC_CONNECT_V2RAY_ALL_PROFILES_V49
#
# V2Ray/Xray credentials are one item per Exit, but one item can carry several
# real customer profiles. The legacy V7 subscription flattened only item.uri,
# which is the selected/recommended profile and silently dropped the remaining
# profiles. Always resolve the final runtime customer policy instead so the
# subscription and Public Connect page expose the same ordered profile set.
# Legacy credentials without usable profiles[] keep their historical item.uri.


def _active_public_payload(token: str, db: Session) -> dict[str, Any]:
    sub = _subscription_from_share_token(token, db)
    status = str(getattr(sub.status, "value", sub.status)).strip().lower()
    if status != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")
    return _public_payload(db, sub)


def _item_v2ray_uris(item: dict[str, Any]) -> list[str]:
    """Return every customer-safe URI for one Xray server in policy order."""

    result: list[str] = []
    seen: set[str] = set()

    for profile in xray_delivery._customer_profiles(item):
        if not isinstance(profile, dict):
            continue
        uri = str(profile.get("uri") or "").strip()
        if not uri or "://" not in uri or uri in seen:
            continue
        seen.add(uri)
        result.append(uri)

    if result:
        return result

    # Compatibility fallback for true legacy credentials. Modern Xray items
    # normally resolve three profiles via the V47 customer policy.
    uri = str(item.get("uri") or "").strip()
    if uri and "://" in uri:
        return [uri]
    return []


def _v2ray_profile_groups(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Group resolved profiles by credential item/server for UI and metadata."""

    groups: list[dict[str, Any]] = []
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        return groups

    for credential in credentials:
        if not isinstance(credential, dict):
            continue
        protocol = str(credential.get("protocol") or "").strip().lower()
        if protocol not in {"v2ray", "xray"}:
            continue
        items = credential.get("items") or []
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            continue

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            uris = _item_v2ray_uris(item)
            if not uris:
                continue

            node_id = item.get("node_id")
            server = str(
                item.get("node")
                or item.get("country")
                or item.get("location")
                or item.get("server")
                or item.get("server_ip")
                or f"Server {index + 1}"
            ).strip()

            profile_rows: list[dict[str, Any]] = []
            resolved_profiles = xray_delivery._customer_profiles(item)
            by_uri = {
                str(profile.get("uri") or "").strip(): profile
                for profile in resolved_profiles
                if isinstance(profile, dict)
                and str(profile.get("uri") or "").strip()
            }
            for uri_index, uri in enumerate(uris):
                profile = by_uri.get(uri) or {}
                profile_rows.append(
                    {
                        "id": str(profile.get("id") or "").strip() or None,
                        "title": str(
                            profile.get("title")
                            or profile.get("profile_title")
                            or profile.get("id")
                            or f"Config {uri_index + 1}"
                        ).strip(),
                        "transport": str(profile.get("transport") or "").strip() or None,
                        "security": str(profile.get("security") or "").strip() or None,
                        "uri": uri,
                    }
                )

            groups.append(
                {
                    "node_id": node_id,
                    "server": server,
                    "profile_count": len(profile_rows),
                    "profiles": profile_rows,
                }
            )

    return groups


def _v2ray_uris(payload: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for group in _v2ray_profile_groups(payload):
        profiles = group.get("profiles") or []
        for profile in profiles if isinstance(profiles, list) else []:
            if not isinstance(profile, dict):
                continue
            uri = str(profile.get("uri") or "").strip()
            if not uri or uri in seen:
                continue
            seen.add(uri)
            result.append(uri)
    return result


def _subscription_content(token: str, db: Session) -> tuple[str, int, int]:
    payload = _active_public_payload(token, db)
    groups = _v2ray_profile_groups(payload)
    uris = []
    seen: set[str] = set()
    for group in groups:
        for profile in group.get("profiles") or []:
            if not isinstance(profile, dict):
                continue
            uri = str(profile.get("uri") or "").strip()
            if not uri or uri in seen:
                continue
            seen.add(uri)
            uris.append(uri)

    if not uris:
        raise HTTPException(
            status_code=404,
            detail="مولتی‌لینک V2Ray برای این اشتراک آماده نیست",
        )
    raw = "\n".join(uris).encode("utf-8")
    return base64.b64encode(raw).decode("ascii"), len(groups), len(uris)


def _subscription_response(token: str, db: Session) -> Response:
    content, server_count, profile_count = _subscription_content(token, db)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Profile-Title": "TwinPanel-V2Ray",
            "Profile-Update-Interval": "12",
            "X-TwinPanel-Server-Count": str(server_count),
            "X-TwinPanel-Profile-Count": str(profile_count),
        },
    )


def _subscription_meta_response(token: str, db: Session) -> JSONResponse:
    payload = _active_public_payload(token, db)
    groups = _v2ray_profile_groups(payload)
    return JSONResponse(
        {
            "protocol": "v2ray",
            "server_count": len(groups),
            "profile_count": sum(int(group.get("profile_count") or 0) for group in groups),
            "servers": groups,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/{token}/subscription/v2ray",
    name="public_v2ray_subscription_v7",
)
def public_v2ray_subscription_v7(
    token: str,
    db: Session = Depends(get_db),
):
    """Return a base64 feed containing every customer-safe V2Ray/Xray profile."""
    return _subscription_response(token, db)


@router.get(
    "/{token}/subscription/v2ray/meta",
    name="public_v2ray_subscription_meta_v49",
)
def public_v2ray_subscription_meta_v49(
    token: str,
    db: Session = Depends(get_db),
):
    """Expose grouped server/profile metadata for the modern Public Connect UI."""
    return _subscription_meta_response(token, db)


# TWINPANEL_PUBLIC_CONNECT_NEUTRAL_SUB_URL_V50
# Some public networks inspect plaintext HTTP paths and interfere when protocol
# product names appear in the URL. Preserve the historical V2Ray routes for
# compatibility, but expose a neutral canonical feed used by Public Connect and
# external clients. The payload, policy and credentials are identical.
@router.get(
    "/{token}/sub",
    name="public_v2ray_subscription_neutral_v50",
)
def public_v2ray_subscription_neutral_v50(
    token: str,
    db: Session = Depends(get_db),
):
    return _subscription_response(token, db)


@router.get(
    "/{token}/sub/meta",
    name="public_v2ray_subscription_neutral_meta_v50",
)
def public_v2ray_subscription_neutral_meta_v50(
    token: str,
    db: Session = Depends(get_db),
):
    return _subscription_meta_response(token, db)


@router.get("/{token}/subscription/v2ray/qr")
def public_v2ray_subscription_qr_v7(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """QR contains the neutral stable subscription URL, not duplicated data."""
    _subscription_content(token, db)
    subscription_url = str(
        request.url_for("public_v2ray_subscription_neutral_v50", token=token)
    )
    image = qrcode.make(subscription_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
