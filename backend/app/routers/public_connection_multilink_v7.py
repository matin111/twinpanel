from __future__ import annotations

import base64
import io
from typing import Any

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from .account_delivery import _public_payload, _subscription_from_share_token


router = APIRouter(
    prefix="/v1/connect",
    tags=["public-connection-multilink-v7"],
)


def _active_public_payload(token: str, db: Session) -> dict[str, Any]:
    sub = _subscription_from_share_token(token, db)
    status = str(getattr(sub.status, "value", sub.status)).strip().lower()
    if status != "active":
        raise HTTPException(status_code=403, detail="اشتراک فعال نیست")
    return _public_payload(db, sub)


def _v2ray_uris(payload: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    credentials = payload.get("credentials") or []
    if not isinstance(credentials, list):
        return result

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
        for item in items:
            if not isinstance(item, dict):
                continue
            uri = str(item.get("uri") or "").strip()
            if not uri or uri in seen:
                continue
            seen.add(uri)
            result.append(uri)
    return result


def _subscription_content(token: str, db: Session) -> str:
    payload = _active_public_payload(token, db)
    uris = _v2ray_uris(payload)
    if not uris:
        raise HTTPException(
            status_code=404,
            detail="مولتی‌لینک V2Ray برای این اشتراک آماده نیست",
        )
    raw = "\n".join(uris).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


@router.get(
    "/{token}/subscription/v2ray",
    name="public_v2ray_subscription_v7",
)
def public_v2ray_subscription_v7(
    token: str,
    db: Session = Depends(get_db),
):
    """Return a standard base64 multi-link feed containing only real V2Ray/Xray URIs."""
    content = _subscription_content(token, db)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{token}/subscription/v2ray/qr")
def public_v2ray_subscription_qr_v7(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """QR contains the stable subscription URL, not duplicated credential data."""
    _subscription_content(token, db)
    subscription_url = str(
        request.url_for("public_v2ray_subscription_v7", token=token)
    )
    image = qrcode.make(subscription_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
