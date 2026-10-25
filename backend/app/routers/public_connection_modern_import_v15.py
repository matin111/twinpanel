from __future__ import annotations

import base64
import copy
import html
import json
import re
from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy.orm import Session

from .account_delivery import _public_payload, _subscription_from_share_token
from .public_connection_modern_delivery_v13 import MODERN_PROTOCOLS, _items, _status_value
from .public_connection_modern_names_v14 import _profile_name


# Karing's own share surface can embed a JSON list of sing-box outbounds in the
# custom ulink:// scheme. This avoids a second HTTP fetch from inside Karing,
# which is especially important when TwinPanel itself is reached through an IP
# or a path that the client cannot fetch while changing network state.
KARING_INLINE_PROTOCOLS = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
}

STANDARD_SHARE_PROTOCOLS = {
    "hysteria2",
    "tuic",
    "anytls",
}


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _host_for_uri(value: Any) -> str:
    host = str(value or "").strip()
    if not host:
        return ""
    if ":" in host and not (host.startswith("[") and host.endswith("]")):
        return f"[{host}]"
    return host


def _outbound(item: dict[str, Any]) -> dict[str, Any] | None:
    outbound = item.get("outbound")
    if isinstance(outbound, dict):
        return dict(outbound)

    raw = str(item.get("config") or "").strip()
    if not raw:
        return None

    try:
        config = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    rows = config.get("outbounds") if isinstance(config, dict) else None
    if not isinstance(rows, list):
        return None

    for row in rows:
        if not isinstance(row, dict):
            continue
        outbound_type = str(row.get("type") or "").strip().lower()
        if outbound_type and outbound_type not in {"direct", "block", "dns"}:
            return dict(row)

    return None


def karing_inline_uri(protocol: str, item: dict[str, Any], profile_name: str) -> str:
    protocol = str(protocol or "").strip().lower()
    if protocol not in KARING_INLINE_PROTOCOLS:
        return ""

    outbound = _outbound(item)
    if not isinstance(outbound, dict):
        return ""
    if str(outbound.get("type") or "").strip().lower() != protocol:
        return ""

    node = copy.deepcopy(outbound)
    node["tag"] = str(profile_name or "TwinPanel").strip() or "TwinPanel"

    raw = json.dumps(
        [node],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    encoded = base64.b64encode(raw).decode("ascii")
    fragment = quote(str(profile_name or "TwinPanel"), safe="")
    return (
        "ulink://install/?content="
        + quote(encoded, safe="")
        + "&format=json#"
        + fragment
    )


def _tls_params(outbound: dict[str, Any]) -> list[tuple[str, str]]:
    tls = outbound.get("tls")
    if not isinstance(tls, dict):
        return []

    params: list[tuple[str, str]] = []
    server_name = str(tls.get("server_name") or "").strip()
    if server_name:
        params.append(("sni", server_name))
    if bool(tls.get("insecure")):
        params.append(("insecure", "1"))
    return params


def standard_share_uri(protocol: str, item: dict[str, Any], profile_name: str) -> str:
    protocol = str(protocol or "").strip().lower()
    if protocol not in STANDARD_SHARE_PROTOCOLS:
        return ""

    outbound = _outbound(item)
    if not isinstance(outbound, dict):
        return ""
    if str(outbound.get("type") or "").strip().lower() != protocol:
        return ""

    host = _host_for_uri(outbound.get("server"))
    try:
        port = int(outbound.get("server_port") or 0)
    except (TypeError, ValueError):
        port = 0
    if not host or not 1 <= port <= 65535:
        return ""

    label = quote(str(profile_name or "TwinPanel"), safe="")

    if protocol == "hysteria2":
        password = str(outbound.get("password") or "")
        if not password:
            return ""
        params = _tls_params(outbound)
        obfs = outbound.get("obfs")
        if isinstance(obfs, dict):
            obfs_type = str(obfs.get("type") or "").strip()
            obfs_password = str(obfs.get("password") or "").strip()
            if obfs_type:
                params.append(("obfs", obfs_type))
            if obfs_password:
                params.append(("obfs-password", obfs_password))
        query = urlencode(params)
        suffix = ("?" + query) if query else ""
        return (
            "hysteria2://"
            + quote(password, safe="")
            + "@"
            + host
            + f":{port}/"
            + suffix
            + "#"
            + label
        )

    if protocol == "tuic":
        uuid = str(outbound.get("uuid") or "").strip()
        password = str(outbound.get("password") or "")
        if not uuid or not password:
            return ""
        params = []
        congestion = str(outbound.get("congestion_control") or "").strip()
        if congestion:
            params.append(("congestion_control", congestion))
        udp_relay = str(outbound.get("udp_relay_mode") or "native").strip()
        if udp_relay:
            params.append(("udp_relay_mode", udp_relay))
        tls = outbound.get("tls")
        if isinstance(tls, dict):
            server_name = str(tls.get("server_name") or "").strip()
            if server_name:
                params.append(("sni", server_name))
            if bool(tls.get("insecure")):
                params.append(("allow_insecure", "1"))
        if bool(outbound.get("zero_rtt_handshake")):
            params.append(("reduce_rtt", "1"))
        query = urlencode(params)
        suffix = ("?" + query) if query else ""
        return (
            "tuic://"
            + quote(uuid, safe="")
            + ":"
            + quote(password, safe="")
            + "@"
            + host
            + f":{port}/"
            + suffix
            + "#"
            + label
        )

    if protocol == "anytls":
        password = str(outbound.get("password") or "")
        if not password:
            return ""
        params: list[tuple[str, str]] = [("security", "tls")]
        params.extend(_tls_params(outbound))
        query = urlencode(params)
        return (
            "anytls://"
            + quote(password, safe="")
            + "@"
            + host
            + f":{port}/?"
            + query
            + "#"
            + label
        )

    return ""


def _replace_remote_karing_button(
    source: str,
    *,
    config_path: str,
    karing_uri: str,
    standard_uri: str,
) -> str:
    escaped_path = _h(config_path)
    pattern = re.compile(
        r'<button class="primary-btn v13-karing-import" type="button" '
        r'data-config-path="'
        + re.escape(escaped_path)
        + r'"[^>]*>افزودن مستقیم به Karing</button>'
    )

    if not pattern.search(source):
        return source

    controls = (
        '<a class="primary-btn v15-karing-inline" '
        f'href="{_h(karing_uri)}">افزودن مستقیم به Karing</a>'
    )
    if standard_uri:
        controls += (
            '<button class="v13-secondary copy-btn v15-standard-link" '
            f'type="button" data-copy="{_h(standard_uri)}">'
            'کپی لینک استاندارد</button>'
        )

    return pattern.sub(controls, source, count=1)


def refine_public_connection_modern_import_v15(
    source: str,
    token: str,
    db: Session,
) -> str:
    """Prefer embedded/direct Modern imports over client-side remote fetches."""
    if "TWINPANEL_PUBLIC_MODERN_IMPORT_V15" in source:
        return source

    sub = _subscription_from_share_token(token, db)
    if _status_value(sub) != "active":
        return source

    payload = _public_payload(db, sub)
    credentials = payload.get("credentials") if isinstance(payload, dict) else []

    for cred in credentials if isinstance(credentials, list) else []:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").strip().lower()
        if protocol not in MODERN_PROTOCOLS:
            continue

        for item in _items(cred):
            try:
                node_id = int(item.get("node_id") or 0)
            except (TypeError, ValueError):
                node_id = 0
            if node_id <= 0:
                continue

            profile_name = _profile_name(sub, protocol, item)
            karing_uri = karing_inline_uri(protocol, item, profile_name)
            if not karing_uri:
                continue

            standard_uri = standard_share_uri(protocol, item, profile_name)
            config_path = (
                f"/v1/connect/{quote(str(token), safe='')}/modern-config-v14/"
                f"{quote(protocol, safe='')}/{node_id}"
            )
            source = _replace_remote_karing_button(
                source,
                config_path=config_path,
                karing_uri=karing_uri,
                standard_uri=standard_uri,
            )

    source = source.replace(
        "</style>",
        """
/* TWINPANEL_PUBLIC_MODERN_IMPORT_V15 */
.v15-karing-inline{white-space:nowrap}
.v15-standard-link{display:inline-flex!important;align-items:center;justify-content:center}
""" + "\n</style>",
        1,
    )
    source = source.replace(
        "</body>",
        "<!-- TWINPANEL_PUBLIC_MODERN_IMPORT_V15 -->\n</body>",
        1,
    )
    return source
