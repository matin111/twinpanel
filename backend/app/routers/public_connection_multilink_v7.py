from __future__ import annotations

import base64
import io
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import xray_profile_reconcile_v36
from .. import xray_public_delivery_runtime as xray_delivery
from .. import subscription_delivery_policy_v1 as delivery_policy
from .. import xray_customer_profile_policy_v30 as customer_policy
from .. import mother_subscription_delivery_policy_v108 as mother_policy
from ..database import get_db
from ..models import Node, ProtocolCredential
from . import account_delivery


router = APIRouter(tags=["public-connection-multilink-v7"])


# TWINPANEL_PUBLIC_CONNECT_V2RAY_ALL_PROFILES_V56
#
# V2Ray/Xray credentials are one item per Exit, but one item must expose exactly
# three real customer profiles under the active V47 policy. Older subscriptions
# may still store only item.uri and have no profiles[]. Those legacy rows are
# reconciled against the existing Xray runtime before /sub or /sub/meta is
# returned. Reconciliation preserves the existing UUID and writes the real
# three-profile credential back to ProtocolCredential; no fake UI duplicates are
# generated here.
#
# Public metadata exposes only customer-safe node identity: display name and
# country code. Public IP, domain, agent URL and other infrastructure details are
# deliberately not returned.


def _subscription_and_payload(token: str, db: Session):
    sub = account_delivery._subscription_from_share_token(token, db)
    status = str(getattr(sub.status, "value", sub.status)).strip().lower()
    if status != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")
    # A V2Ray-only client poll must not decode every other protocol, produce
    # unrelated files/QRs, or run synchronous provisioning. Keep explicit
    # delivery-policy subscriptions on their canonical, policy-aware route.
    if delivery_policy.is_explicit_policy(db, sub.id):
        return sub, account_delivery._public_payload(db, sub)

    cred = (
        db.query(ProtocolCredential)
        .filter(
            ProtocolCredential.subscription_id == sub.id,
            ProtocolCredential.protocol == "v2ray",
            ProtocolCredential.is_active.is_(True),
        ).first()
    )
    if not cred:
        return sub, {"credentials": []}

    raw_items = account_delivery._dec(cred.config_text_encrypted)
    raw_items = (
        raw_items if isinstance(raw_items, list)
        else [raw_items] if isinstance(raw_items, dict) else []
    )
    can_use_mother = mother_policy._subscription_can_use_mother(db, sub)
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        live = account_delivery._live_client_item(db, sub, "v2ray", raw)
        if not account_delivery._delivery_item_is_usable(db, "v2ray", live):
            continue
        if not can_use_mother and mother_policy._item_is_mother(db, live):
            continue
        safe = customer_policy._customer_xray_item_v261(db, live)
        if safe is not None:
            items.append(safe)
    return sub, {
        "credentials": ([{"protocol": "v2ray", "items": items}] if items else []),
    }


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


def _active_public_payload(token: str, db: Session) -> dict[str, Any]:
    """Serve stored, deliverable Xray profiles without remote repair on GET.

    HTTP subscription downloads must never initiate SSH provisioning: clients
    may poll every few seconds, and one incomplete Exit must not block the
    already-working profiles of other Exits. Repair remains a separate job.
    """
    _sub, payload = _subscription_and_payload(token, db)
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

    # Legacy accounts can retain a single VLESS URI without profiles[].
    # Serve that stored URI until independent provisioning builds real profiles;
    # do not synthesize unavailable transports during HTTP GET.
    if not result and not isinstance(item.get("profiles"), list):
        uri = str(item.get("uri") or "").strip()
        if uri.startswith("vless://"):
            result.append(uri)
    return result


def _customer_safe_node_meta(db: Session, item: dict[str, Any], index: int) -> tuple[str, str | None]:
    try:
        node_id = int(item.get("node_id") or 0)
    except (TypeError, ValueError):
        node_id = 0

    node = db.get(Node, node_id) if node_id else None
    if node is None:
        return f"سرور {index + 1}", None

    display_name = str(getattr(node, "name", "") or "").strip() or f"سرور {index + 1}"
    country_code = str(getattr(node, "country_code", "") or "").strip().upper() or None
    return display_name, country_code


# TWINPANEL_XRAY_LIVE_NODE_SUBSCRIPTION_V1
# Per-user credentials are immutable here. An explicit node-level setting
# changes the next subscription response, with no SSH/provisioning on GET.
# The corresponding server-side REALITY inbound must be updated first.
_HOSTNAME = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")


def _live_xray_settings(db: Session, payload: dict[str, Any]) -> dict[int, dict[str, str]]:
    ids = set()
    for item in _v2ray_items(payload):
        try:
            node_id = int(item.get("node_id") or 0)
        except (ValueError, TypeError):
            continue
        if node_id > 0:
            ids.add(node_id)
    if not ids:
        return {}

    # One bulk database lookup, independent of account and profile counts.
    rows = db.execute(
        text(
            "SELECT node_id, settings_json FROM modern_protocol_settings "
            "WHERE protocol = 'v2ray' AND node_id = ANY(:node_ids)"
        ),
        {"node_ids": sorted(ids)},
    ).all()
    result: dict[int, dict[str, str]] = {}
    for node_id, raw in rows:
        try:
            settings = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        if not isinstance(settings, dict):
            continue
        override = {}
        for key in ("reality_server_name", "tls_server_name"):
            hostname = str(settings.get(key) or "").lower().strip()
            if (
                hostname
                and _HOSTNAME.fullmatch(hostname)
                and ".." not in hostname
                and all(len(label) <= 63 for label in hostname.split("."))
            ):
                override[key] = hostname
        if override:
            result[int(node_id)] = override
    return result


def _apply_live_xray_uri(uri: str, settings: dict[str, str]) -> str:
    """Patch only public TLS/REALITY SNI; never touch UUID, keys or route."""
    if not settings or not uri.startswith("vless://"):
        return uri
    try:
        parsed = urlsplit(uri)
        params = parse_qsl(parsed.query, keep_blank_values=True)
        security = next((value.lower() for key, value in params if key == "security"), "")
        key = {
            "reality": "reality_server_name",
            "tls": "tls_server_name",
        }.get(security)
        sni = settings.get(key) if key else None
        if not sni:
            return uri
        updated = [(k, sni if k == "sni" else v) for k, v in params]
        if not any(k == "sni" for k, _ in updated):
            updated.append(("sni", sni))
        if security == "tls":
            updated = [(k, sni if k == "host" else v) for k, v in updated]
        return urlunsplit(parsed._replace(query=urlencode(updated)))
    except (TypeError, ValueError):
        return uri


def _v2ray_profile_groups(db: Session, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Group resolved profiles by server and include only customer-safe location metadata."""

    groups: list[dict[str, Any]] = []
    live_settings = _live_xray_settings(db, payload)
    for item in _v2ray_items(payload):
        try:
            node_id = int(item.get("node_id") or 0)
        except (TypeError, ValueError):
            node_id = 0
        node_settings = live_settings.get(node_id, {})
        uris = [_apply_live_xray_uri(uri, node_settings) for uri in _item_v2ray_uris(item)]
        if not uris:
            continue

        profile_rows: list[dict[str, Any]] = []
        resolved_profiles = xray_delivery._customer_profiles(item)
        by_uri = {
            _apply_live_xray_uri(str(profile.get("uri") or "").strip(), node_settings): profile
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

        server_name, country_code = _customer_safe_node_meta(db, item, len(groups))
        groups.append(
            {
                "node_id": item.get("node_id"),
                "server": server_name,
                "country_code": country_code,
                "profile_count": len(profile_rows),
                "profiles": profile_rows,
            }
        )

    return groups


def _v2ray_uris(db: Session, payload: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for group in _v2ray_profile_groups(db, payload):
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
    groups = _v2ray_profile_groups(db, payload)
    uris = list(dict.fromkeys(
        str(profile.get("uri") or "").strip()
        for group in groups
        for profile in group.get("profiles", [])
        if isinstance(profile, dict) and str(profile.get("uri") or "").strip()
    ))
    if not uris:
        raise HTTPException(
            status_code=503,
            detail="هنوز کانفیگ V2Ray قابل دریافت برای این اشتراک وجود ندارد",
        )
    return base64.b64encode("\n".join(uris).encode("utf-8")).decode("ascii"), len(groups), len(uris)


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
    groups = _v2ray_profile_groups(db, payload)
    if not groups:
        raise HTTPException(
            status_code=503,
            detail="هنوز کانفیگ V2Ray قابل دریافت برای این اشتراک وجود ندارد",
        )
    return JSONResponse(
        {
            "protocol": "v2ray",
            "server_count": len(groups),
            "profile_count": sum(int(g["profile_count"]) for g in groups),
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
    """Return a base64 feed containing exactly three real profiles per server."""
    return _subscription_response(token, db)


@router.get(
    "/{token}/subscription/v2ray/meta",
    name="public_v2ray_subscription_meta_v49",
)
def public_v2ray_subscription_meta_v49(
    token: str,
    db: Session = Depends(get_db),
):
    """Expose grouped exact-three metadata for the Public Connect UI."""
    return _subscription_meta_response(token, db)


# TWINPANEL_PUBLIC_CONNECT_NEUTRAL_SUB_URL_V50
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