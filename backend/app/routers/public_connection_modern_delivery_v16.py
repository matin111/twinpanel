from __future__ import annotations

import copy
import html
import json
import re
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
    _ready_modern_item,
    _status_value,
)
from .public_connection_modern_import_v15 import KARING_126_PROTOCOLS, _outbound
from .public_connection_modern_names_v14 import _download_stem, _profile_name


router = APIRouter(tags=["public-connection-modern-delivery-v16"])


_V16_MARKER = "TWINPANEL_PUBLIC_MODERN_DELIVERY_V16"


def _h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _resolve_delivery_content(
    protocol: str,
    item: dict[str, Any],
    profile_name: str,
) -> tuple[str, str, str] | None:
    """Return (content, extension, media_type) without inventing protocol data.

    Raw generated config always wins. This is especially important for Naive,
    where the full JSON contains the managed CA trust material. If raw config is
    absent, use the canonical share URI already stored by Account Delivery. As a
    final lossless fallback, serialize the canonical outbound that Account
    Delivery already exposes; never synthesize protocol-specific fields here.
    """
    protocol = str(protocol or "").strip().lower()
    config = str(item.get("config") or "").strip()
    config_format = str(item.get("config_format") or "").strip().lower()

    if config:
        if config_format in {"sing-box", "mieru-json", "sudoku-json"}:
            return config, "json", "application/json"
        if protocol == "amneziawg" or config_format in {
            "amneziawg",
            "amneziawg-conf",
        }:
            return config, "conf", "text/plain"
        return config, "txt", "text/plain"

    uri = str(item.get("uri") or "").strip()
    if uri:
        return uri, "txt", "text/plain"

    outbound = _outbound(item)
    if not isinstance(outbound, dict):
        return None

    node = copy.deepcopy(outbound)
    node["tag"] = str(profile_name or "TwinPanel").strip() or "TwinPanel"
    content = json.dumps(
        {"outbounds": [node]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return content, "json", "application/json"


def _replace_unsupported_karing_button(
    source: str,
    *,
    protocol: str,
    config_path: str,
) -> str:
    """Replace stale V13 one-click Karing actions for the 1.2.26-only cohort."""
    if protocol not in KARING_126_PROTOCOLS:
        return source

    escaped_path = _h(config_path)
    pattern = re.compile(
        r'<button class="primary-btn v13-karing-import" type="button" '
        r'data-config-path="'
        + re.escape(escaped_path)
        + r'"(?: data-config-name="[^"]*")?[^>]*>'
        r'افزودن مستقیم به Karing</button>'
    )
    replacement = (
        f'<a class="primary-btn tp-v16-safe-download" href="{escaped_path}">'
        'دانلود کانفیگ</a>'
    )
    return pattern.sub(replacement, source, count=1)


@router.get("/{token}/modern-config-v16/{protocol}/{node_id}")
def public_modern_config_v16(
    token: str,
    protocol: str,
    node_id: int,
    db: Session = Depends(get_db),
):
    protocol = str(protocol or "").strip().lower()
    if protocol not in MODERN_PROTOCOLS:
        raise HTTPException(status_code=404, detail="پروتکل پشتیبانی نمی‌شود")

    sub = _subscription_from_share_token(token, db)
    item = _ready_modern_item(token, protocol, node_id, db)
    profile_name = _profile_name(sub, protocol, item)
    resolved = _resolve_delivery_content(protocol, item, profile_name)
    if resolved is None:
        raise HTTPException(
            status_code=409,
            detail="برای این سرور هنوز کانفیگ قابل تحویل ساخته نشده است",
        )

    content, extension, media_type = resolved
    stem = _download_stem(sub, protocol, item)
    filename = f"{stem}.{extension}"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def refine_public_connection_modern_delivery_v16(
    source: str,
    token: str,
    db: Session,
) -> str:
    """Repair only broken Modern download actions after V15 refinement."""
    if _V16_MARKER in source:
        return source

    sub = _subscription_from_share_token(token, db)
    if _status_value(sub) != "active":
        return source

    payload = _public_payload(db, sub)
    credentials = payload.get("credentials") if isinstance(payload, dict) else []
    token_part = quote(str(token), safe="")

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
            resolved = _resolve_delivery_content(protocol, item, profile_name)
            if resolved is None:
                continue

            old_path = (
                f"/v1/connect/{token_part}/modern-config-v14/"
                f"{quote(protocol, safe='')}/{node_id}"
            )
            current_path = old_path

            # V14 is already correct when the canonical raw config exists. Only
            # move genuinely broken downloads to V16, preserving healthy paths.
            if not str(item.get("config") or "").strip():
                new_path = (
                    f"/v1/connect/{token_part}/modern-config-v16/"
                    f"{quote(protocol, safe='')}/{node_id}"
                )
                source = source.replace(_h(old_path), _h(new_path))
                current_path = new_path

            # Karing 1.2.25 must never be advertised as one-click capable for
            # Snell/Sudoku/TrustTunnel. V15 already supplies a copy action; the
            # old V13 button becomes a real download instead.
            source = _replace_unsupported_karing_button(
                source,
                protocol=protocol,
                config_path=current_path,
            )

    source = source.replace(
        "</body>",
        f"<!-- {_V16_MARKER} -->\n</body>",
        1,
    )
    return source
