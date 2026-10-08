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

    Admin-created domains are the source of truth. The newest active
    domain wins, so adding/replacing an API domain immediately becomes
    effective without rebuilding the frontend or changing environment
    variables. Domains whose nginx setup failed are never advertised.
    """

    base = (
        db.query(Domain)
        .filter(
            Domain.domain_type == domain_type,
            Domain.is_active.is_(True),
            Domain.nginx_status == "active",
        )
    )

    # Prefer the newest domain that already has SSL.
    item = (
        base
        .filter(Domain.ssl_status == SSLStatus.ACTIVE)
        .order_by(Domain.id.desc())
        .first()
    )

    # Until SSL issuance finishes, the newest working HTTP domain is
    # still a valid temporary public origin.
    if item is None:
        item = (
            base
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
    # 1) As soon as admin adds a working API domain, use it.
    value = _domain_origin(db, DomainType.API)
    if value:
        return value

    # 2) Before a domain exists, use the configured public IP/base.
    value = _clean_base(settings.public_api_fallback)
    if value:
        return value

    # 3) Last-resort auto discovery from the incoming request host.
    value = request_origin(request)
    if value:
        return value

    # Compatibility fallback for installations that have another
    # public service domain but no dedicated API domain yet.
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
