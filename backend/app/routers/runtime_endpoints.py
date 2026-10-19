from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..domain_models import Domain, DomainType, SSLStatus
from ..models import Subscription, SubscriptionStatus
from ..quota_models import QuotaSession, QuotaUsageEvent
from ..services.public_urls import api_base_url
from .admin import dashboard_summary_v2


router = APIRouter(tags=["runtime"])


# Keep this window identical to the public Connect live-state rule. Xray's
# StatsService exposes cumulative traffic rather than authoritative open/close
# events, so a recent positive accepted delta is the safest live signal.
_XRAY_LIVE_ACTIVITY_SECONDS = 30


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


def _online_subscription_ids(db: Session) -> set[int]:
    active_session_ids = {
        int(row[0])
        for row in (
            db.query(QuotaSession.subscription_id)
            .join(Subscription, Subscription.id == QuotaSession.subscription_id)
            .filter(
                Subscription.status == SubscriptionStatus.ACTIVE,
                QuotaSession.status == "active",
            )
            .distinct()
            .all()
        )
    }

    xray_cutoff = datetime.utcnow() - timedelta(seconds=_XRAY_LIVE_ACTIVITY_SECONDS)
    recent_xray_ids = {
        int(row[0])
        for row in (
            db.query(QuotaUsageEvent.subscription_id)
            .join(Subscription, Subscription.id == QuotaUsageEvent.subscription_id)
            .filter(
                Subscription.status == SubscriptionStatus.ACTIVE,
                QuotaUsageEvent.protocol == "xray",
                QuotaUsageEvent.accepted_bytes > 0,
                QuotaUsageEvent.reported_at >= xray_cutoff,
            )
            .distinct()
            .all()
        )
    }

    # A subscription connected on more than one protocol is still one online
    # subscription on the dashboard, so union the identifiers before counting.
    return active_session_ids | recent_xray_ids


@router.get("/v1/runtime/endpoints")
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


@router.get(
    "/v1/admin/dashboard-summary",
    dependencies=[Depends(require_admin)],
)
def dashboard_summary_live_subscriptions(db: Session = Depends(get_db)):
    """Admin dashboard summary with protocol-aware online subscriptions.

    This route is registered before the legacy admin router. It deliberately
    preserves every legacy summary field while replacing the old node-agent
    ``current_users`` estimate with canonical quota telemetry. ``online_users``
    remains as a compatibility alias for older frontends.
    """

    payload = dict(dashboard_summary_v2(db))
    online_subscriptions = len(_online_subscription_ids(db))
    payload["online_subscriptions"] = online_subscriptions
    payload["online_users"] = online_subscriptions
    return payload
