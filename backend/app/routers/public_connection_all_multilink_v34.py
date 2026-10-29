from __future__ import annotations

import base64
import copy
import io
import json
import re
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from .account_delivery import _public_payload, _subscription_from_share_token
from .public_connection_modern_delivery_v13 import _items, _sudoku_uri
from .public_connection_modern_import_v15 import _outbound, standard_share_uri
from .public_connection_modern_names_v14 import _profile_name
from .public_connection_modern_delivery_v16 import _resolve_delivery_content


router = APIRouter(tags=["public-connect-all-multilink-v34"])

_MARKER = "TWINPANEL_PUBLIC_CONNECT_ALL_MULTILINK_V34"

# Cisco and L2TP are the only manual Server/User/Password protocols.
MULTI_PROTOCOLS = (
    "openvpn",
    "wireguard",
    "v2ray",
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
)

# Native clients consume files, not a synthetic share URI. Their one public URL
# therefore downloads one ZIP containing every real country/node configuration.
NATIVE_BUNDLE_PROTOCOLS = {"openvpn", "wireguard", "amneziawg"}

PROTOCOL_TITLES = {
    "openvpn": "OpenVPN",
    "wireguard": "WireGuard",
    "v2ray": "V2Ray / Xray",
    "hysteria2": "Hysteria2",
    "tuic": "TUIC",
    "anytls": "AnyTLS",
    "naive": "NaiveProxy",
    "shadowtls": "ShadowTLS",
    "snell": "Snell",
    "mieru": "Mieru",
    "trusttunnel": "TrustTunnel",
    "amneziawg": "AmneziaWG",
    "sudoku": "Sudoku",
}

PROTOCOL_CLIENT = {
    "openvpn": "openvpn",
    "wireguard": "wireguard",
    "v2ray": "hiddify",
    "hysteria2": "karing",
    "tuic": "karing",
    "anytls": "karing",
    "naive": "karing",
    "shadowtls": "karing",
    "snell": "hiddify",
    "mieru": "karing",
    "trusttunnel": "trusttunnel",
    "amneziawg": "amneziawg",
    "sudoku": "sudoku",
}


def _normalize(value: Any) -> str:
    protocol = str(value or "").strip().lower()
    if protocol == "xray":
        return "v2ray"
    if protocol == "naiveproxy":
        return "naive"
    return protocol


def _active(token: str, db: Session) -> tuple[Any, dict[str, Any]]:
    sub = _subscription_from_share_token(token, db)
    status = str(getattr(sub.status, "value", sub.status) or "").strip().lower()
    if status != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")
    payload = _public_payload(db, sub)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=404, detail="اطلاعات اتصال آماده نیست")
    return sub, payload


def _protocol_items(payload: dict[str, Any], protocol: str) -> list[dict[str, Any]]:
    protocol = _normalize(protocol)
    result: list[dict[str, Any]] = []
    credentials = payload.get("credentials") or []
    for credential in credentials if isinstance(credentials, list) else []:
        if not isinstance(credential, dict):
            continue
        if _normalize(credential.get("protocol")) != protocol:
            continue
        result.extend(_items(credential))
    return result


def _safe_name(value: Any, fallback: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip(".-")
    return name[:100] or fallback


def _item_name(item: dict[str, Any], index: int) -> str:
    return str(
        item.get("profile_name")
        or item.get("node")
        or item.get("country")
        or item.get("location")
        or f"Server-{index + 1}"
    ).strip()


def _share_uri(sub: Any, protocol: str, item: dict[str, Any]) -> str:
    protocol = _normalize(protocol)
    profile = _profile_name(sub, protocol, item)

    if protocol in {"hysteria2", "tuic", "anytls"}:
        generated = str(standard_share_uri(protocol, item, profile) or "").strip()
        if generated:
            return generated

    uri = str(item.get("uri") or "").strip()
    if protocol == "sudoku" and not uri:
        uri = str(_sudoku_uri(item) or "").strip()
    return uri if "://" in uri else ""


def _all_share_uris(sub: Any, protocol: str, items: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for item in items:
        uri = _share_uri(sub, protocol, item)
        if not uri:
            return []
        if uri in seen:
            continue
        seen.add(uri)
        rows.append(uri)
    return rows


def _all_outbounds(protocol: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        outbound = _outbound(item)
        if not isinstance(outbound, dict):
            return []
        node = copy.deepcopy(outbound)
        node["tag"] = _item_name(item, index)
        rows.append(node)
    return rows


def _bundle_item(
    protocol: str,
    sub: Any,
    item: dict[str, Any],
    index: int,
) -> tuple[str, bytes] | None:
    raw_config = str(item.get("config") or "").strip()
    name = _safe_name(_item_name(item, index), f"server-{index + 1}")

    if protocol == "openvpn" and raw_config:
        filename = str(item.get("filename") or f"{name}.ovpn")
        return _safe_name(filename, f"{name}.ovpn"), raw_config.encode("utf-8")

    if protocol in {"wireguard", "amneziawg"} and raw_config:
        filename = str(item.get("filename") or f"{name}.conf")
        return _safe_name(filename, f"{name}.conf"), raw_config.encode("utf-8")

    profile = _profile_name(sub, protocol, item)
    resolved = _resolve_delivery_content(protocol, item, profile)
    if resolved is not None:
        content, extension, _media_type = resolved
        return f"{name}.{_safe_name(extension, 'txt')}", str(content).encode("utf-8")

    uri = _share_uri(sub, protocol, item)
    if uri:
        return f"{name}.txt", uri.encode("utf-8")
    return None


def _bundle(protocol: str, sub: Any, items: list[dict[str, Any]]) -> bytes:
    out = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, item in enumerate(items):
            resolved = _bundle_item(protocol, sub, item, index)
            if resolved is None:
                continue
            filename, content = resolved
            base = filename
            suffix = 2
            while filename in used:
                stem, dot, ext = base.rpartition(".")
                filename = f"{stem or base}-{suffix}{dot}{ext}" if dot else f"{base}-{suffix}"
                suffix += 1
            used.add(filename)
            archive.writestr(filename, content)
    if not used:
        raise HTTPException(status_code=404, detail="کانفیگ قابل تحویل برای این پروتکل پیدا نشد")
    return out.getvalue()


def _delivery(
    token: str,
    protocol: str,
    db: Session,
) -> tuple[str, int, Any, list[dict[str, Any]], Any]:
    protocol = _normalize(protocol)
    if protocol not in MULTI_PROTOCOLS:
        raise HTTPException(status_code=404, detail="مولتی‌لینک برای این پروتکل ارائه نمی‌شود")

    sub, payload = _active(token, db)
    items = _protocol_items(payload, protocol)
    if not items:
        raise HTTPException(status_code=404, detail="سرور آماده‌ای برای این پروتکل وجود ندارد")

    if protocol in NATIVE_BUNDLE_PROTOCOLS:
        return "bundle", len(items), sub, items, None

    uris = _all_share_uris(sub, protocol, items)
    if uris:
        return "uri", len(uris), sub, items, uris

    outbounds = _all_outbounds(protocol, items)
    if outbounds:
        return "singbox", len(outbounds), sub, items, outbounds

    return "bundle", len(items), sub, items, None


def _headers(protocol: str, kind: str, count: int) -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Profile-Title": f"TwinPanel-{protocol}",
        "Profile-Update-Interval": "12",
        "X-TwinPanel-Protocol": protocol,
        "X-TwinPanel-Node-Count": str(count),
        "X-TwinPanel-Multi-Kind": kind,
        "X-TwinPanel-Client": PROTOCOL_CLIENT.get(protocol, ""),
    }


@router.get("/{token}/multi/{protocol}/meta", name="public_protocol_multi_meta_v34")
def public_protocol_multi_meta_v34(
    token: str,
    protocol: str,
    db: Session = Depends(get_db),
):
    protocol = _normalize(protocol)
    kind, count, _sub, _items_list, _payload = _delivery(token, protocol, db)
    return JSONResponse(
        {
            "protocol": protocol,
            "title": PROTOCOL_TITLES.get(protocol, protocol),
            "kind": kind,
            "node_count": count,
            "client": PROTOCOL_CLIENT.get(protocol),
            "can_copy_as_subscription": kind in {"uri", "singbox"},
            "is_bundle": kind == "bundle",
        },
        headers=_headers(protocol, kind, count),
    )


@router.get("/{token}/multi/{protocol}", name="public_protocol_multi_v34")
def public_protocol_multi_v34(
    token: str,
    protocol: str,
    db: Session = Depends(get_db),
):
    protocol = _normalize(protocol)
    kind, count, sub, items, payload = _delivery(token, protocol, db)
    headers = _headers(protocol, kind, count)

    if kind == "uri":
        raw = "\n".join(payload).encode("utf-8")
        content = base64.b64encode(raw).decode("ascii")
        headers["Content-Disposition"] = f'inline; filename="twinpanel-{protocol}-subscription.txt"'
        return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)

    if kind == "singbox":
        headers["Content-Disposition"] = f'inline; filename="twinpanel-{protocol}-singbox.json"'
        return Response(
            content=json.dumps({"outbounds": payload}, ensure_ascii=False, separators=(",", ":")),
            media_type="application/json; charset=utf-8",
            headers=headers,
        )

    blob = _bundle(protocol, sub, items)
    headers["Content-Disposition"] = f'attachment; filename="twinpanel-{protocol}-all-servers.zip"'
    return Response(content=blob, media_type="application/zip", headers=headers)


__all__ = [
    "router",
    "MULTI_PROTOCOLS",
    "NATIVE_BUNDLE_PROTOCOLS",
    "PROTOCOL_CLIENT",
    "_active",
    "_bundle",
    "_normalize",
    "_protocol_items",
    "_MARKER",
]
