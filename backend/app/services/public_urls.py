from __future__ import annotations

import re

from fastapi import Request
from sqlalchemy.orm import Session

from ..domain_models import (
    Domain,
    DomainType,
    SSLStatus,
)


def _domain_origin(
    db: Session,
    domain_type: DomainType,
) -> str | None:

    query = (
        db.query(Domain)
        .filter(
            Domain.domain_type == domain_type,
            Domain.is_active.is_(True),
        )
        .order_by(Domain.id.asc())
    )

    item = (
        query
        .filter(
            Domain.ssl_status == SSLStatus.ACTIVE
        )
        .first()
    )

    if item is None:
        item = query.first()

    if item is None:
        return None

    domain = str(
        item.domain or ""
    ).strip().lower()

    if not domain:
        return None

    scheme = (
        "https"
        if item.ssl_status == SSLStatus.ACTIVE
        else "http"
    )

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

    scheme = (
        forwarded_proto
        or str(request.url.scheme or "http").lower()
    )

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

    value = _domain_origin(
        db,
        DomainType.API,
    )

    if value:
        return value

    value = request_origin(request)

    if value:
        return value

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

    value = _domain_origin(
        db,
        DomainType.SUBSCRIPTION,
    )

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

    return None


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

    return None
