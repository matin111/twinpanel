"""On-demand, subscription-scoped QR images for the public connection page.

Only the initial HTML renderer enables deferral. Existing API responses and
client configuration generation continue using the original inline PNG format.
The encrypted QR source never appears in plaintext in URLs or server logs.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import quote

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db


router = APIRouter(tags=["public-connection-qr"])
_page_share_token: ContextVar[str | None] = ContextVar(
    "twinpanel_public_connection_page_qr", default=None
)
_MAX_QR_TEXT_BYTES = 16384
_QR_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60


@contextmanager
def defer_public_connection_qr(token: str):
    """Opt in only while rendering one customer's initial public HTML page."""
    scope = _page_share_token.set(str(token))
    try:
        yield
    finally:
        _page_share_token.reset(scope)


def deferred_qr_src(value: str) -> str | None:
    token = _page_share_token.get()
    if not token:
        return None

    raw = str(value).encode("utf-8")
    if not raw or len(raw) > _MAX_QR_TEXT_BYTES:
        return None

    # Reuse the same authenticated-encryption key as account delivery. QR
    # contents (including VPN secrets) must not be sent in plaintext URLs.
    from .account_delivery import _fernet

    sealed = _fernet().encrypt(raw).decode("ascii")
    return (
        f"/v1/connect/{quote(token, safe='')}/qr-image"
        f"?v={quote(sealed, safe='')}"
    )


@router.get("/{token}/qr-image")
def public_connection_qr_image(
    token: str,
    v: str = Query(..., min_length=30, max_length=24576),
    db: Session = Depends(get_db),
) -> Response:
    from .account_delivery import _fernet, _qr_data_uri, _subscription_from_share_token

    # An encrypted image URL is not an authorization bypass: every request
    # must still resolve a currently active customer share token.
    sub = _subscription_from_share_token(token, db)
    status = str(getattr(sub.status, "value", sub.status)).lower()
    if status != "active":
        raise HTTPException(status_code=404, detail="QR not available")

    try:
        raw = _fernet().decrypt(v.encode("ascii"), ttl=_QR_TOKEN_TTL_SECONDS)
        if not raw or len(raw) > _MAX_QR_TEXT_BYTES:
            raise ValueError("QR text is empty or too large")
        value = raw.decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError):
        raise HTTPException(status_code=404, detail="QR not available")

    # This endpoint is outside the page-render context, so the original QR
    # generator returns a PNG data URI, not another deferred URL.
    inline = _qr_data_uri(value)
    if not inline.startswith("data:image/png;base64,"):
        raise HTTPException(status_code=500, detail="QR generation failed")
    data = base64.b64decode(inline.partition(",")[2])
    return Response(
        content=data,
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )
