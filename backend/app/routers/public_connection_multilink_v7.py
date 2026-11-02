from __future__ import annotations

import base64
import io
from typing import Any

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from .. import xray_profile_reconcile_v36
from .. import xray_public_delivery_runtime as xray_delivery
from ..database import get_db
from ..models import Node
from . import account_delivery


router = APIRouter(tags=["public-connection-multilink-v7"])


# TWINPANEL_PUBLIC_CONNECT_V2RAY_ALL_PROFILES_V55
#
# V2Ray/Xray credentials are one item per Exit, but one item must expose exactly
# three real customer profiles under the active V47 policy. Older subscriptions
# may still store only item.uri and have no profiles[]. Those legacy rows are
# reconciled against the existing Xray runtime before /sub or /sub/meta is
# returned. Reconciliation preserves the existing UUID and writes the real
# three-profile credential back to ProtocolCredential; no fake UI duplicates are
# generated here.
#
# Public metadata always uses neutral Server N labels. Real node/country/host
# names are intentionally not exposed by this UI metadata surface.


def _subscription_and_payload(token: str, db: Session):
    sub = account_delivery._subscription_from_share_token(token, db)
    status = str(getattr(sub.status, "value", sub.status)).strip().lower()
    if status != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")
    return sub, account_delivery._public_payload(db, sub)


def _v2ray_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        return output
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
        output.extend(item for item in items if isinstance(item, dict))
    return output


def _profile_count(item: dict[str, Any]) -> int:
    return len(
        [
            profile
            for profile in xray_delivery._customer_profiles(item)
            if isinstance(profile, dict)
            and str(profile.get("uri") or "").strip()
        ]
    )


async def _active_public_payload(token: str, db: Session) -> dict[str, Any]:
    """Return an exact-three V2Ray payload, reconciling legacy rows in place."""

    sub, payload = _subscription_and_payload(token, db)
    missing_nodes: list[Node] = []
    seen_node_ids: set[int] = set()

    for item in _v2ray_items(payload):
        if _profile_count(item) == 3:
            continue
        try:
            node_id = int(item.get("node_id") or 0)
        except (TypeError, ValueError):
            continue
        if not node_id or node_id in seen_node_ids:
            continue
        node = db.get(Node, node_id)
        if node is None:
            continue
        seen_node_ids.add(node_id)
        missing_nodes.append(node)

    errors: list[str] = []
    for node in missing_nodes:
        try:
            await xray_profile_reconcile_v36._reconcile_subscription_for_exit(
                db,
                sub,
                node,
            )
        except Exception as exc:
            db.rollback()
            errors.append(str(exc)[:240])

    if missing_nodes:
        payload = account_delivery._public_payload(db, sub)

    incomplete = [
        item
        for item in _v2ray_items(payload)
        if _profile_count(item) != 3
    ]
    if incomplete:
        detail = "کانفیگ‌های V2Ray این اشتراک هنوز کامل نشده‌اند"
        if errors:
            detail += "؛ آماده‌سازی خودکار ناموفق بود"
        raise HTTPException(status_code=503, detail=detail)

    return payload


def _item_v2ray_uris(item: dict[str, Any]) -> list[str]:
    """Return exactly three real customer-safe URIs in active policy order."""

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

    return result if len(result) == 3 else []


def _v2ray_profile_groups(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Group resolved profiles by credential item while hiding server identity."""

    groups: list[dict[str, Any]] = []
    for item in _v2ray_items(payload):
        uris = _item_v2ray_uris(item)
        if len(uris) != 3:
            continue

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
                "node_id": item.get("node_id"),
                "server": f"سرور {len(groups) + 1}",
                "profile_count": 3,
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


async def _subscription_content(token: str, db: Session) -> tuple[str, int, int]:
    payload = await _active_public_payload(token, db)
    groups = _v2ray_profile_groups(payload)
    uris = _v2ray_uris(payload)

    if not uris or not groups or len(uris) != len(groups) * 3:
        raise HTTPException(
            status_code=503,
            detail="مولتی‌لینک V2Ray هنوز سه کانفیگ کامل برای هر سرور ندارد",
        )
    raw = "\n".join(uris).encode("utf-8")
    return base64.b64encode(raw).decode("ascii"), len(groups), len(uris)


async def _subscription_response(token: str, db: Session) -> Response:
    content, server_count, profile_count = await _subscription_content(token, db)
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


async def _subscription_meta_response(token: str, db: Session) -> JSONResponse:
    payload = await _active_public_payload(token, db)
    groups = _v2ray_profile_groups(payload)
    if not groups or any(int(group.get("profile_count") or 0) != 3 for group in groups):
        raise HTTPException(
            status_code=503,
            detail="نمایش V2Ray هنوز سه کانفیگ کامل برای هر سرور ندارد",
        )
    return JSONResponse(
        {
            "protocol": "v2ray",
            "server_count": len(groups),
            "profile_count": len(groups) * 3,
            "servers": groups,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/{token}/subscription/v2ray",
    name="public_v2ray_subscription_v7",
)
async def public_v2ray_subscription_v7(
    token: str,
    db: Session = Depends(get_db),
):
    """Return a base64 feed containing exactly three real profiles per server."""
    return await _subscription_response(token, db)


@router.get(
    "/{token}/subscription/v2ray/meta",
    name="public_v2ray_subscription_meta_v49",
)
async def public_v2ray_subscription_meta_v49(
    token: str,
    db: Session = Depends(get_db),
):
    """Expose grouped exact-three metadata for the Public Connect UI."""
    return await _subscription_meta_response(token, db)


# TWINPANEL_PUBLIC_CONNECT_NEUTRAL_SUB_URL_V50
@router.get(
    "/{token}/sub",
    name="public_v2ray_subscription_neutral_v50",
)
async def public_v2ray_subscription_neutral_v50(
    token: str,
    db: Session = Depends(get_db),
):
    return await _subscription_response(token, db)


@router.get(
    "/{token}/sub/meta",
    name="public_v2ray_subscription_neutral_meta_v50",
)
async def public_v2ray_subscription_neutral_meta_v50(
    token: str,
    db: Session = Depends(get_db),
):
    return await _subscription_meta_response(token, db)


@router.get("/{token}/subscription/v2ray/qr")
async def public_v2ray_subscription_qr_v7(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """QR contains the neutral stable subscription URL, not duplicated data."""
    await _subscription_content(token, db)
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
