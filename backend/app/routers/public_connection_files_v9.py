from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from .account_delivery import _public_payload, _subscription_from_share_token


router = APIRouter(tags=["public-connection-files-v9"])

_FILE_TYPES = {
    "openvpn": ("ovpn", "application/x-openvpn-profile"),
    "wireguard": ("conf", "application/octet-stream"),
}


def _active_payload(token: str, db: Session) -> dict[str, Any]:
    sub = _subscription_from_share_token(token, db)
    status = str(getattr(sub.status, "value", sub.status)).strip().lower()
    if status != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")
    return _public_payload(db, sub)


def _items_for_protocol(payload: dict[str, Any], protocol: str) -> list[dict[str, Any]]:
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        return []
    for credential in credentials:
        if not isinstance(credential, dict):
            continue
        current = str(credential.get("protocol") or "").strip().lower()
        if current != protocol:
            continue
        raw = credential.get("items") or []
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        return [dict(item) for item in raw if isinstance(item, dict)]
    return []


def _safe_filename(value: Any, protocol: str, index: int) -> str:
    extension = _FILE_TYPES[protocol][0]
    fallback = f"{protocol}-{index + 1}.{extension}"
    raw = str(value or "").strip()
    if not raw:
        return fallback
    base = raw.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-")
    if not base:
        return fallback
    if not base.lower().endswith(f".{extension}"):
        base = f"{base}.{extension}"
    return base[:120]


@router.get(
    "/{token}/file/{protocol}/{item_index}",
    name="public_connection_file_v9",
)
def public_connection_file_v9(
    token: str,
    protocol: str,
    item_index: int,
    db: Session = Depends(get_db),
):
    """Return a real downloadable profile file instead of a browser-generated text Blob."""
    protocol = str(protocol or "").strip().lower()
    if protocol not in _FILE_TYPES:
        raise HTTPException(status_code=404, detail="فایل این پروتکل پشتیبانی نمی‌شود")
    if item_index < 0:
        raise HTTPException(status_code=404, detail="فایل پیدا نشد")

    payload = _active_payload(token, db)
    items = _items_for_protocol(payload, protocol)
    if item_index >= len(items):
        raise HTTPException(status_code=404, detail="فایل پیدا نشد")

    item = items[item_index]
    config = str(item.get("config") or "").strip()
    if not config:
        raise HTTPException(status_code=404, detail="کانفیگ هنوز آماده نیست")

    filename = _safe_filename(item.get("filename"), protocol, item_index)
    media_type = _FILE_TYPES[protocol][1]
    return Response(
        content=config.encode("utf-8"),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
