from __future__ import annotations

import base64
import html
import json
import re
import secrets
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from .account_delivery import _public_payload, _subscription_from_share_token
from .public_connection_modern_delivery_v13 import (
    MODERN_PROTOCOLS,
    _items,
    _mieru_karing_yaml,
    _ready_modern_item,
    _status_value,
    _sudoku_uri,
)


router = APIRouter(tags=["public-connection-modern-names-v14"])

_ALLOWED_COMPONENT = re.compile(r"[^A-Za-z0-9_=+.-]+")


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _safe_component(value: Any, fallback: str) -> str:
    raw = str(value if value is not None else "").strip()
    safe = _ALLOWED_COMPONENT.sub("-", raw).strip("-._=+")
    return safe or fallback


def _account_name(sub: Any) -> str:
    username = _safe_component(getattr(sub, "account_username", None), "")
    if username:
        return username
    subscription_id = int(getattr(sub, "id", 0) or 0)
    return f"user-{subscription_id}" if subscription_id > 0 else "user"


def _node_name(item: dict[str, Any]) -> str:
    node_id = int(item.get("node_id") or 0)
    return _safe_component(item.get("node"), f"node-{node_id or 0}")


def _profile_name(sub: Any, protocol: str, item: dict[str, Any]) -> str:
    username = _account_name(sub)
    country = _node_name(item)
    node_id = int(item.get("node_id") or 0)
    protocol_name = _safe_component(protocol, "vpn")
    return f"{username}-{country}-{protocol_name}-{node_id}"


def _download_stem(sub: Any, protocol: str, item: dict[str, Any]) -> str:
    username = _account_name(sub)
    country = _node_name(item)
    node_id = int(item.get("node_id") or 0)
    protocol_name = _safe_component(protocol, "vpn")

    if protocol_name == "amneziawg":
        # AmneziaWG/WireGuard for Windows derives the tunnel name from the
        # filename. It allows only [A-Za-z0-9_=+.-] and at most 32 characters.
        # Give every download a fresh safe suffix so Chrome never has to create
        # an invalid " (1)" duplicate filename.
        country = country[:8].rstrip("-._=+") or "node"
        suffix = f"-{country}-amneziawg-{secrets.token_hex(2)}"
        room = max(1, 32 - len(suffix))
        prefix = username[:room].rstrip("-._=+") or "u"
        return f"{prefix}{suffix}"

    stem = f"{username}-{country}-{protocol_name}-{node_id}"
    return stem[:96].rstrip("-._=+") or f"user-{protocol_name}-{node_id}"


def _named_sudoku_uri(item: dict[str, Any], profile_name: str) -> str:
    uri = _sudoku_uri(item)
    if not uri.startswith("sudoku://"):
        return uri
    token = uri.removeprefix("sudoku://")
    try:
        padded = token + "=" * ((4 - len(token) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        return uri
    if not isinstance(payload, dict):
        return uri
    payload["n"] = profile_name
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sudoku://" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _named_mieru_karing_yaml(item: dict[str, Any], profile_name: str) -> str:
    content = _mieru_karing_yaml(item)
    if not content:
        return ""
    old = json.dumps("TwinPanel Mieru", ensure_ascii=False)
    new = json.dumps(profile_name, ensure_ascii=False)
    return content.replace(old, new)


@router.get("/{token}/modern-config-v14/{protocol}/{node_id}")
def public_modern_config_v14(
    token: str,
    protocol: str,
    node_id: int,
    profile: str | None = None,
    db: Session = Depends(get_db),
):
    protocol = str(protocol or "").strip().lower()
    if protocol not in MODERN_PROTOCOLS:
        raise HTTPException(status_code=404, detail="پروتکل پشتیبانی نمی‌شود")

    sub = _subscription_from_share_token(token, db)
    item = _ready_modern_item(token, protocol, node_id, db)
    config = str(item.get("config") or "").strip()
    if not config:
        raise HTTPException(status_code=404, detail="کانفیگ آماده نیست")

    profile_name = _profile_name(sub, protocol, item)
    stem = _download_stem(sub, protocol, item)

    if protocol == "mieru" and str(profile or "").strip().lower() == "karing":
        content = _named_mieru_karing_yaml(item, profile_name)
        if not content:
            raise HTTPException(status_code=404, detail="پروفایل Karing آماده نیست")
        filename = f"{stem}.yaml"
        media_type = "text/yaml"
    else:
        config_format = str(item.get("config_format") or "").strip().lower()
        if config_format in {"sing-box", "mieru-json", "sudoku-json"}:
            filename = f"{stem}.json"
            media_type = "application/json"
        elif protocol == "amneziawg" or config_format in {"amneziawg", "amneziawg-conf"}:
            filename = f"{stem}.conf"
            media_type = "text/plain"
        else:
            filename = f"{stem}.txt"
            media_type = "text/plain"
        content = config

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def refine_public_connection_modern_names_v14(source: str, token: str, db: Session) -> str:
    """Apply customer username + node/country naming after V13 delivery."""
    if "TWINPANEL_PUBLIC_MODERN_NAMES_V14" in source:
        return source

    sub = _subscription_from_share_token(token, db)
    if _status_value(sub) != "active":
        return source

    old_prefix = (
        f"/v1/connect/{quote(str(token), safe='')}/modern-config/"
    )
    new_prefix = (
        f"/v1/connect/{quote(str(token), safe='')}/modern-config-v14/"
    )
    source = source.replace(old_prefix, new_prefix)

    payload = _public_payload(db, sub)
    credentials = payload.get("credentials") if isinstance(payload, dict) else []

    for cred in credentials if isinstance(credentials, list) else []:
        if not isinstance(cred, dict):
            continue
        protocol = str(cred.get("protocol") or "").strip().lower()
        if protocol not in MODERN_PROTOCOLS:
            continue

        for item in _items(cred):
            node_id = int(item.get("node_id") or 0)
            if node_id <= 0:
                continue
            profile_name = _profile_name(sub, protocol, item)
            path = (
                f"{new_prefix}{quote(protocol, safe='')}/{node_id}"
            )
            marker = f'data-config-path="{_h(path)}"'
            source = source.replace(
                marker,
                marker + f' data-config-name="{_h(profile_name)}"',
                1,
            )

            if protocol == "mieru":
                marker = f'data-config-path="{_h(path)}?profile=karing"'
                source = source.replace(
                    marker,
                    marker + f' data-config-name="{_h(profile_name)}"',
                    1,
                )

            if protocol == "sudoku" and not str(item.get("uri") or "").strip():
                old_uri = _sudoku_uri(item)
                new_uri = _named_sudoku_uri(item, profile_name)
                if old_uri and new_uri and old_uri != new_uri:
                    source = source.replace(_h(old_uri), _h(new_uri), 1)

    source = source.replace(
        "encodeURIComponent('TwinPanel')",
        "encodeURIComponent(button.dataset.configName||'user')",
        1,
    )
    source = source.replace(
        "</body>",
        "<!-- TWINPANEL_PUBLIC_MODERN_NAMES_V14 -->\n</body>",
        1,
    )
    return source
