from __future__ import annotations

import re

from fastapi import Request
from sqlalchemy.orm import Session

from ..config import settings
from ..domain_models import (
    Domain,
    DomainType,
    SSLStatus,
)


def _clean_base(value: str | None) -> str | None:
    cleaned = str(value or "").strip().rstrip("/")
    return cleaned or None


def _domain_origin(
    db: Session,
    domain_type: DomainType,
) -> str | None:
    """Return the newest usable domain for a service role.

    The newest active domain with a working Nginx config wins. This is
    intentional: when an admin adds/replaces the API domain, the public
    base switches to that domain immediately. SSL may still be pending;
    in that short window the resolver advertises http:// and automatically
    becomes https:// as soon as SSLStatus turns ACTIVE.
    """

    item = (
        db.query(Domain)
        .filter(
            Domain.domain_type == domain_type,
            Domain.is_active.is_(True),
            Domain.nginx_status == "active",
        )
        .order_by(Domain.id.desc())
        .first()
    )

    if item is None:
        return None

    domain = str(item.domain or "").strip().lower()
    if not domain:
        return None

    scheme = "https" if item.ssl_status == SSLStatus.ACTIVE else "http"
    return f"{scheme}://{domain}"


def request_origin(
    request: Request | None,
) -> str | None:
    if request is None:
        return None

    forwarded_proto = (
        request.headers
        .get("x-forwarded-proto", "")
        .split(",")[0]
        .strip()
        .lower()
    )

    scheme = forwarded_proto or str(request.url.scheme or "http").lower()
    if scheme not in {"http", "https"}:
        scheme = "http"

    forwarded_host = (
        request.headers
        .get("x-forwarded-host", "")
        .split(",")[0]
        .strip()
    )

    host = (
        forwarded_host
        or request.headers.get("host", "").strip()
        or str(request.url.netloc or "").strip()
    )

    if (
        not host
        or re.search(r"[\s/\\\\]", host)
        or "\r" in host
        or "\n" in host
    ):
        return None

    return f"{scheme}://{host}".rstrip("/")


def api_base_url(
    db: Session,
    request: Request | None = None,
) -> str | None:
    # 1) Admin domain wins immediately when its Nginx config is active.
    value = _domain_origin(db, DomainType.API)
    if value:
        return value

    # 2) Before a domain exists, use the configured public IP/base URL.
    value = _clean_base(settings.public_api_fallback)
    if value:
        return value

    # 3) Last-resort auto discovery from the incoming request host.
    value = request_origin(request)
    if value:
        return value

    # Compatibility fallback for installations that already expose
    # another public service role but have no API domain yet.
    for kind in (
        DomainType.PANEL,
        DomainType.SHOP,
        DomainType.SUBSCRIPTION,
    ):
        value = _domain_origin(db, kind)
        if value:
            return value

    return None


def subscription_base_url(
    db: Session,
    request: Request | None = None,
) -> str | None:
    value = _domain_origin(db, DomainType.SUBSCRIPTION)
    if value:
        return value

    value = request_origin(request)
    if value:
        return value

    for kind in (
        DomainType.SHOP,
        DomainType.PANEL,
        DomainType.API,
    ):
        value = _domain_origin(db, kind)
        if value:
            return value

    return _clean_base(settings.public_api_fallback)


def shop_base_url(
    db: Session,
    request: Request | None = None,
) -> str | None:
    for kind in (
        DomainType.SHOP,
        DomainType.PANEL,
    ):
        value = _domain_origin(db, kind)
        if value:
            return value

    value = request_origin(request)
    if value:
        return value

    for kind in (
        DomainType.API,
        DomainType.SUBSCRIPTION,
    ):
        value = _domain_origin(db, kind)
        if value:
            return value

    return _clean_base(settings.public_api_fallback)
