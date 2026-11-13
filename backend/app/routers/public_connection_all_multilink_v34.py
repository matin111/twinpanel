from __future__ import annotations

import base64
import copy
import io
import json
import re
import zipfile
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..openvpn_profile_delivery_guard_v1 import validate_openvpn_profile
from .account_delivery import _public_payload, _subscription_from_share_token
from .public_connection_modern_delivery_v13 import _items, _sudoku_uri
from .public_connection_modern_import_v15 import _outbound, standard_share_uri
from .public_connection_modern_names_v14 import (
    _account_name,
    _named_mieru_karing_yaml,
    _named_sudoku_uri,
    _profile_name,
)
from .public_connection_modern_delivery_v16 import _resolve_delivery_content
from .public_connection_multilink_v7 import _subscription_and_payload, _v2ray_items, _subscription_content, _subscription_usage_headers
from .. import xray_public_delivery_runtime as xray_delivery


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
    "socks5",
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
    "socks5": "SOCKS5 Proxy",
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
    "socks5": "singbox",
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


def _multilink_name(sub: Any, protocol: str) -> str:
    protocol_name = _safe_name(_normalize(protocol), "vpn")
    return f"{_account_name(sub)}-{protocol_name}"


def _named_uri(uri: str, profile: str) -> str:
    uri = str(uri or "").strip()
    if "://" not in uri:
        return ""
    base = uri.split("#", 1)[0]
    return base + "#" + quote(str(profile or "user"), safe="")


def _share_uri(sub: Any, protocol: str, item: dict[str, Any]) -> str:
    protocol = _normalize(protocol)
    # The subscription title represents the whole group, while every server
    # remark must remain individually identifiable inside Karing/Hiddify.
    profile = _profile_name(sub, protocol, item)

    if protocol in {"hysteria2", "tuic", "anytls"}:
        generated = str(standard_share_uri(protocol, item, profile) or "").strip()
        if generated:
            return generated

    uri = str(item.get("uri") or "").strip()
    if protocol == "sudoku":
        named = _named_sudoku_uri(item, profile)
        if named and "://" in named:
            return named
        if not uri:
            uri = str(_sudoku_uri(item) or "").strip()
    return _named_uri(uri, profile) if "://" in uri else ""


def _all_share_uris(sub: Any, protocol: str, items: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for item in items:
        if protocol == "v2ray":
            profiles = xray_delivery._customer_profiles(item)
            if profiles:
                for profile in profiles:
                    uri = str(profile.get("uri") or "").strip()
                    if not uri or "://" not in uri:
                        continue
                    label = _profile_name(sub, protocol, item)
                    label += "-" + _safe_name(profile.get("id"), "profile")
                    named = _named_uri(uri, label)
                    if named and named not in seen:
                        seen.add(named)
                        rows.append(named)
                continue
        uri = _share_uri(sub, protocol, item)
        if not uri:
            return []
        if uri in seen:
            continue
        seen.add(uri)
        rows.append(uri)
    return rows


def _all_outbounds(sub: Any, protocol: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        outbound = _outbound(item)
        if not isinstance(outbound, dict):
            return []
        node = copy.deepcopy(outbound)
        node["tag"] = _profile_name(sub, protocol, item)
        rows.append(node)
    return rows


def _shadowtls_multi_karing_yaml(sub: Any, items: list[dict[str, Any]]) -> str:
    rows = ["proxies:"]
    names: list[str] = []
    q = lambda value: json.dumps(str(value), ensure_ascii=False)
    for item in items:
        raw = str(item.get("config") or "").strip()
        if not raw:
            return ""
        try:
            config = json.loads(raw)
        except Exception:
            return ""
        outbounds = config.get("outbounds") if isinstance(config, dict) else None
        if not isinstance(outbounds, list):
            return ""
        ss = next((x for x in outbounds if isinstance(x, dict) and str(x.get("type") or "").lower()=="shadowsocks"), None)
        st = next((x for x in outbounds if isinstance(x, dict) and str(x.get("type") or "").lower()=="shadowtls"), None)
        if not isinstance(ss, dict) or not isinstance(st, dict):
            return ""
        profile = _profile_name(sub, "shadowtls", item)
        server = str(st.get("server") or "").strip()
        try:
            port = int(st.get("server_port") or 0)
        except Exception:
            port = 0
        method = str(ss.get("method") or "").strip()
        ss_password = str(ss.get("password") or "")
        st_password = str(st.get("password") or "")
        tls = st.get("tls") if isinstance(st.get("tls"), dict) else {}
        host = str(tls.get("server_name") or "").strip()
        version = int(st.get("version") or 3)
        if not server or not (1 <= port <= 65535) or not method or not ss_password or not st_password or not host:
            return ""
        names.append(profile)
        rows.extend([
            f"  - name: {q(profile)}",
            "    type: ss",
            f"    server: {q(server)}",
            f"    port: {port}",
            f"    cipher: {q(method)}",
            f"    password: {q(ss_password)}",
            "    udp: true",
            "    plugin: shadow-tls",
            "    client-fingerprint: chrome",
            "    plugin-opts:",
            f"      host: {q(host)}",
            f"      password: {q(st_password)}",
            f"      version: {version}",
        ])
    if not names:
        return ""
    group = _multilink_name(sub, "shadowtls")
    rows.extend(["proxy-groups:", f"  - name: {q(group)}", "    type: select", "    proxies:"])
    rows.extend(f"      - {q(name)}" for name in names)
    rows.extend(["rules:", f"  - MATCH,{group}", ""])
    return "\n".join(rows)


def _shadowtls_multi_singbox_json(items: list[dict[str, Any]]) -> str:
    """Losslessly compose full SS->ShadowTLS pairs for sing-box-aware importers.

    Unlike an isolated ShadowTLS outbound, each Shadowsocks outbound retains
    its detour to the matching transport.  Do not copy multiple local inbounds,
    which would duplicate their listen port.
    """
    outbounds: list[dict[str, Any]] = []
    seen: set[str] = set()
    first_proxy = ""
    for item in items:
        try:
            config = json.loads(str(item.get("config") or ""))
            candidates = config.get("outbounds", [])
            ss = next(x for x in candidates if isinstance(x, dict) and x.get("type") == "shadowsocks")
            st = next(x for x in candidates if isinstance(x, dict) and x.get("type") == "shadowtls")
            ss_tag = str(ss.get("tag") or "").strip()
            st_tag = str(st.get("tag") or "").strip()
            if not ss_tag or not st_tag or ss.get("detour") != st_tag:
                return ""
            if ss_tag in seen or st_tag in seen or ss_tag == st_tag:
                return ""
            if not (ss.get("method") and ss.get("password") and st.get("server") and st.get("server_port") and st.get("password")):
                return ""
            seen.update((ss_tag, st_tag))
            if not first_proxy:
                first_proxy = ss_tag
            outbounds.extend((ss, st))
        except (ValueError, TypeError, KeyError, StopIteration, AttributeError):
            return ""
    if not outbounds:
        return ""
    return json.dumps(
        {"log": {"level": "warn"}, "outbounds": outbounds, "route": {"final": first_proxy}},
        ensure_ascii=False, indent=2,
    )


def _mieru_multi_karing_yaml(sub: Any, items: list[dict[str, Any]]) -> str:
    proxy_blocks: list[list[str]] = []
    names: list[str] = []
    for item in items:
        profile = _profile_name(sub, "mieru", item)
        content = _named_mieru_karing_yaml(item, profile)
        if not content:
            return ""
        lines = content.splitlines()
        try:
            start = lines.index("proxies:") + 1
            end = lines.index("proxy-groups:")
        except ValueError:
            return ""
        block = lines[start:end]
        if not block:
            return ""
        proxy_blocks.append(block)
        names.append(profile)

    if not proxy_blocks:
        return ""

    q = lambda value: json.dumps(str(value), ensure_ascii=False)
    group = _multilink_name(sub, "mieru")
    rows = ["proxies:"]
    for block in proxy_blocks:
        rows.extend(block)
    rows.extend([
        "proxy-groups:",
        f"  - name: {q(group)}",
        "    type: select",
        "    proxies:",
    ])
    rows.extend(f"      - {q(name)}" for name in names)
    rows.extend([
        "rules:",
        f"  - MATCH,{group}",
        "",
    ])
    return "\n".join(rows)


def _bundle_item(
    protocol: str,
    sub: Any,
    item: dict[str, Any],
    index: int,
) -> tuple[str, bytes] | None:
    raw_config = str(item.get("config") or "").strip()
    name = _safe_name(_item_name(item, index), f"server-{index + 1}")

    if protocol == "openvpn" and raw_config:
        try:
            validate_openvpn_profile(raw_config)
        except ValueError as exc:
            # Do not embed a missing-remote profile into the bulk ZIP.
            raise HTTPException(status_code=409, detail=str(exc)) from None
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
    db.info.setdefault("_tp_public_delivery_tunnels", {})
    protocol = _normalize(protocol)
    if protocol not in MULTI_PROTOCOLS:
        raise HTTPException(status_code=404, detail="مولتی‌لینک برای این پروتکل ارائه نمی‌شود")

    # Poll only the requested Xray credentials: never deserialize or reconcile
    # all unrelated protocols when a client refreshes its V2Ray subscription.
    if protocol == "v2ray":
        sub, payload = _subscription_and_payload(token, db)
    else:
        info = getattr(db, "info", None)
        if isinstance(info, dict):
            info["_tp_public_feed_only_protocol"] = protocol
        try:
            sub, payload = _active(token, db)
        finally:
            if isinstance(info, dict):
                info.pop("_tp_public_feed_only_protocol", None)
    items = _v2ray_items(payload) if protocol == "v2ray" else _protocol_items(payload, protocol)
    if not items:
        raise HTTPException(status_code=404, detail="سرور آماده‌ای برای این پروتکل وجود ندارد")

    if protocol in NATIVE_BUNDLE_PROTOCOLS:
        return "bundle", len(items), sub, items, None

    if protocol == "shadowtls":
        karing_yaml = _shadowtls_multi_karing_yaml(sub, items)
        if karing_yaml:
            return "karing", len(items), sub, items, karing_yaml

    uris = _all_share_uris(sub, protocol, items)
    if uris:
        return "uri", len(uris), sub, items, uris

    if protocol == "mieru":
        karing_yaml = _mieru_multi_karing_yaml(sub, items)
        if karing_yaml:
            return "karing", len(items), sub, items, karing_yaml

    outbounds = _all_outbounds(sub, protocol, items)
    if outbounds:
        return "singbox", len(outbounds), sub, items, outbounds

    return "bundle", len(items), sub, items, None


def _headers(sub: Any, protocol: str, kind: str, count: int) -> dict[str, str]:
    return {
        "Cache-Control": "no-store",
        "Profile-Title": _multilink_name(sub, protocol),
        "Profile-Update-Interval": "12",
        **_subscription_usage_headers(sub),
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
    if protocol == "v2ray":
        # One canonical feed for /sub, /multi/v2ray and metadata.
        _content, server_count, count = _subscription_content(token, db)
        sub = _subscription_from_share_token(token, db)
        kind = "uri"
        return JSONResponse(
            {"protocol": protocol, "title": PROTOCOL_TITLES[protocol],
             "kind": kind, "node_count": count, "server_count": server_count,
             "client": PROTOCOL_CLIENT.get(protocol),
             "can_copy_as_subscription": True, "is_bundle": False},
            headers=_headers(sub, protocol, kind, count),
        )
    kind, count, sub, _items_list, _payload = _delivery(token, protocol, db)
    return JSONResponse(
        {
            "protocol": protocol,
            "title": PROTOCOL_TITLES.get(protocol, protocol),
            "kind": kind,
            "node_count": count,
            "client": PROTOCOL_CLIENT.get(protocol),
            "can_copy_as_subscription": kind in {"uri", "singbox", "karing"},
            "is_bundle": kind == "bundle",
        },
        headers=_headers(sub, protocol, kind, count),
    )


@router.get("/{token}/multi/{protocol}", name="public_protocol_multi_v34")
def public_protocol_multi_v34(
    token: str,
    protocol: str,
    format: str | None = None,
    db: Session = Depends(get_db),
):
    protocol = _normalize(protocol)
    if protocol == "v2ray":
        content, server_count, count = _subscription_content(token, db)
        sub = _subscription_from_share_token(token, db)
        headers = _headers(sub, protocol, "uri", count)
        headers["X-TwinPanel-Server-Count"] = str(server_count)
        headers["X-TwinPanel-Profile-Count"] = str(count)
        headers["Content-Disposition"] = (
            f'inline; filename="{_safe_name(_multilink_name(sub, protocol), "user-vpn")}-subscription.txt"'
        )
        return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)
    kind, count, sub, items, payload = _delivery(token, protocol, db)
    headers = _headers(sub, protocol, kind, count)

    # Explicitly requested portable sing-box config. Default remains the
    # existing Karing/Mihomo YAML, so installed subscriptions stay compatible.
    if protocol == "shadowtls" and str(format or "").lower() == "singbox":
        content = _shadowtls_multi_singbox_json(items)
        if not content:
            raise HTTPException(status_code=409, detail="کانفیگ کامل sing-box آماده نیست")
        headers["Content-Disposition"] = f'inline; filename="{_safe_name(_multilink_name(sub, protocol), "user-vpn")}-singbox.json"'
        headers["X-TwinPanel-Multi-Kind"] = "singbox"
        return Response(content=content, media_type="application/json; charset=utf-8", headers=headers)

    if kind == "uri":
        raw = "\n".join(payload).encode("utf-8")
        content = base64.b64encode(raw).decode("ascii")
        headers["Content-Disposition"] = f'inline; filename="{_safe_name(_multilink_name(sub, protocol), "user-vpn")}-subscription.txt"'
        return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)

    if kind == "karing":
        headers["Content-Disposition"] = f'inline; filename="{_safe_name(_multilink_name(sub, protocol), "user-vpn")}.yaml"'
        return Response(content=str(payload), media_type="text/yaml; charset=utf-8", headers=headers)

    if kind == "singbox":
        headers["Content-Disposition"] = f'inline; filename="{_safe_name(_multilink_name(sub, protocol), "user-vpn")}-singbox.json"'
        return Response(
            content=json.dumps({"outbounds": payload}, ensure_ascii=False, separators=(",", ":")),
            media_type="application/json; charset=utf-8",
            headers=headers,
        )

    blob = _bundle(protocol, sub, items)
    headers["Content-Disposition"] = f'attachment; filename="{_safe_name(_multilink_name(sub, protocol), "user-vpn")}-all-servers.zip"'
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
