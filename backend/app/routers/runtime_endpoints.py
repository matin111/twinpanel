from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..domain_models import Domain, DomainType, SSLStatus
from ..services.public_urls import api_base_url


router = APIRouter(
    prefix="/v1/runtime",
    tags=["runtime"],
)


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
    """Public runtime endpoint discovery.

    Before a dedicated API domain exists, ``api_base`` resolves to the
    configured public server IP/base URL. As soon as an admin adds a
    working API domain, the newest active API domain becomes primary.
    No frontend rebuild or service restart is required for discovery.
    """

    item = _active_api_domain(db)
    base = api_base_url(db, request)

    if item is not None and base:
        return {
            "api_base": base,
            "source": "domain",
            "api_domain": item.domain,
            "ssl_active": item.ssl_status == SSLStatus.ACTIVE,
        }

    return {
        "api_base": base,
        "source": "ip",
        "api_domain": None,
        "ssl_active": False,
    }
