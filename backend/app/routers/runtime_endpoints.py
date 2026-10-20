from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import bot_texts as _bot_text_runtime  # noqa: F401 - installs main bot runtime override
from ..database import get_db
from ..deps import require_admin, require_reseller
from ..domain_models import Domain, DomainType, SSLStatus
from ..models import Subscription, SubscriptionStatus
from ..models_reseller import Reseller, ResellerSubscription
from ..quota_models import QuotaSession, QuotaUsageEvent
from ..services.dashboard_revenue import dashboard_revenue
from ..services.public_urls import api_base_url
from ..services.sales_analytics import (
    admin_sales_analytics as build_admin_sales_analytics,
    reseller_sales_analytics as build_reseller_sales_analytics,
)
from .admin import dashboard_summary_v2


router = APIRouter(tags=["runtime"])


# Keep this window identical to the public Connect live-state rule. Protocols
# with authoritative QuotaSession rows use those directly. Recent accepted
# traffic is also considered so counter-driven protocols such as Xray can
# expose a useful live state without inventing permanent sessions.
_LIVE_ACTIVITY_SECONDS = 30


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


def _normalized_protocol(value: str | None) -> str:
    protocol = str(value or "").strip().lower()
    if protocol == "v2ray":
        return "xray"
    if protocol in {"openconnect", "ocserv", "anyconnect"}:
        return "cisco"
    return protocol


def _subscription_live_states(db: Session) -> dict[int, dict]:
    states: dict[int, dict] = {}

    for subscription_id, protocol, last_seen_at in (
        db.query(
            QuotaSession.subscription_id,
            QuotaSession.protocol,
            func.max(QuotaSession.last_seen_at),
        )
        .join(Subscription, Subscription.id == QuotaSession.subscription_id)
        .filter(
            Subscription.status == SubscriptionStatus.ACTIVE,
            QuotaSession.status == "active",
        )
        .group_by(QuotaSession.subscription_id, QuotaSession.protocol)
        .all()
    ):
        sid = int(subscription_id)
        item = states.setdefault(
            sid,
            {"subscription_id": sid, "online": False, "protocols": set(), "last_seen_at": None},
        )
        normalized = _normalized_protocol(protocol)
        if normalized:
            item["protocols"].add(normalized)
        item["online"] = True
        if last_seen_at is not None and (
            item["last_seen_at"] is None or last_seen_at > item["last_seen_at"]
        ):
            item["last_seen_at"] = last_seen_at

    cutoff = datetime.utcnow() - timedelta(seconds=_LIVE_ACTIVITY_SECONDS)
    for subscription_id, protocol, reported_at in (
        db.query(
            QuotaUsageEvent.subscription_id,
            QuotaUsageEvent.protocol,
            func.max(QuotaUsageEvent.reported_at),
        )
        .join(Subscription, Subscription.id == QuotaUsageEvent.subscription_id)
        .filter(
            Subscription.status == SubscriptionStatus.ACTIVE,
            QuotaUsageEvent.accepted_bytes > 0,
            QuotaUsageEvent.reported_at >= cutoff,
        )
        .group_by(QuotaUsageEvent.subscription_id, QuotaUsageEvent.protocol)
        .all()
    ):
        sid = int(subscription_id)
        item = states.setdefault(
            sid,
            {"subscription_id": sid, "online": False, "protocols": set(), "last_seen_at": None},
        )
        normalized = _normalized_protocol(protocol)
        if normalized:
            item["protocols"].add(normalized)
        item["online"] = True
        if reported_at is not None and (
            item["last_seen_at"] is None or reported_at > item["last_seen_at"]
        ):
            item["last_seen_at"] = reported_at

    return states


def _online_subscription_ids(db: Session) -> set[int]:
    return set(_subscription_live_states(db))


def _live_item(subscription_id: int, states: dict[int, dict]) -> dict:
    state = states.get(subscription_id)
    protocols = sorted(state["protocols"]) if state else []
    last_seen_at = state["last_seen_at"] if state else None
    return {
        "subscription_id": subscription_id,
        "online": bool(state and state["online"]),
        "protocols": protocols,
        "last_seen_at": last_seen_at.isoformat() + "Z" if last_seen_at else None,
    }


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
    """Admin dashboard summary with live state and canonical revenue."""

    # This router is included before the legacy/admin-isolation routers and is
    # therefore the production winner for this exact path. The legacy summary
    # still supplies account/node/protocol counters, but its historical
    # subscription-count `sales_*` values must never escape to the UI.
    payload = dict(dashboard_summary_v2(db))
    payload.update(dashboard_revenue(db))

    online_subscriptions = len(_online_subscription_ids(db))
    payload["online_subscriptions"] = online_subscriptions
    payload["online_users"] = online_subscriptions
    return payload


@router.get(
    "/v1/admin/sales-analytics",
    dependencies=[Depends(require_admin)],
)
def admin_sales_analytics(
    range_name: str = Query(
        default="daily",
        alias="range",
        pattern="^(daily|weekly|monthly|yearly)$",
    ),
    db: Session = Depends(get_db),
):
    """Authoritative confirmed-payment analytics for the admin panel."""

    return build_admin_sales_analytics(db, range_name)


@router.get("/v1/reseller/sales-analytics")
def reseller_sales_analytics(
    range_name: str = Query(
        default="daily",
        alias="range",
        pattern="^(daily|weekly|monthly|yearly)$",
    ),
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    """Sales analytics scoped strictly to the authenticated reseller."""

    return build_reseller_sales_analytics(
        db,
        reseller_id=int(reseller.id),
        range_name=range_name,
    )


@router.get(
    "/v1/admin/subscriptions/live-status",
    dependencies=[Depends(require_admin)],
)
def admin_subscription_live_status(db: Session = Depends(get_db)):
    """Return per-subscription live state for the admin subscriptions table."""

    states = _subscription_live_states(db)
    active_ids = {
        int(row[0])
        for row in db.query(Subscription.id)
        .filter(Subscription.status == SubscriptionStatus.ACTIVE)
        .all()
    }

    return {
        "items": [_live_item(subscription_id, states) for subscription_id in sorted(active_ids, reverse=True)],
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "activity_window_seconds": _LIVE_ACTIVITY_SECONDS,
    }


@router.get("/v1/reseller/subscriptions/live-status")
def reseller_subscription_live_status(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    """Return live state only for subscriptions owned by the authenticated reseller.

    The response intentionally includes an offline item for every visible owned
    subscription. That makes newly-created subscriptions deterministic in the UI
    instead of leaving the connection column blank until traffic exists.
    """

    owned_ids = [
        int(row[0])
        for row in (
            db.query(ResellerSubscription.subscription_id)
            .join(Subscription, Subscription.id == ResellerSubscription.subscription_id)
            .filter(
                ResellerSubscription.reseller_id == reseller.id,
                Subscription.status != SubscriptionStatus.CANCELED,
            )
            .order_by(Subscription.id.desc())
            .all()
        )
    ]
    states = _subscription_live_states(db)

    return {
        "items": [_live_item(subscription_id, states) for subscription_id in owned_ids],
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "activity_window_seconds": _LIVE_ACTIVITY_SECONDS,
    }
