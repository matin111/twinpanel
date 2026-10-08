from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..domain_models import Domain, DomainType, SSLStatus


router = APIRouter(
    prefix="/v1/runtime",
    tags=["runtime"],
)


def _clean_base(value: str | None) -> str:
    return str(value or "").strip().rstrip("/")


def _active_api_domain(db: Session) -> Domain | None:
    return (
        db.query(Domain)
        .filter(
            Domain.domain_type == DomainType.API,
            Domain.is_active.is_(True),
            Domain.nginx_status == "active",
        )
        .order_by(Domain.id.desc())
        .first()
    )


@router.get("/endpoints")
def runtime_endpoints(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public runtime endpoint discovery.

    Before an API domain is configured, clients use the configured
    public IP/base URL. As soon as an active API domain exists in the
    admin domain manager, the public API base automatically switches
    to that domain. No frontend rebuild is required.
    """

    item = _active_api_domain(db)

    if item is not None:
        scheme = (
            "https"
            if item.ssl_status == SSLStatus.ACTIVE
            else "http"
        )

        return {
            "api_base": f"{scheme}://{item.domain}",
            "source": "domain",
            "api_domain": item.domain,
            "ssl_active": item.ssl_status == SSLStatus.ACTIVE,
        }

    fallback = _clean_base(
        settings.public_api_fallback
    )

    if not fallback:
        fallback = _clean_base(
            str(request.base_url)
        )

    return {
        "api_base": fallback,
        "source": "ip",
        "api_domain": None,
        "ssl_active": False,
    }
