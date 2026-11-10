"""Dedicated two-field TwinConnect login and authorized delivery.

App username/password are never equal to VPN credentials, and the share link
is delivered as a separate field. No app password appears in a public URL.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..central_app_credentials import (
    app_delivery_payload, authenticate_app, rotate_app_credentials,
    verify_app_session,
)
from ..central_app_identity import central_app_entitled, installation_namespace, subscription_app_namespace
from ..database import get_db
from ..deps import get_current_user, require_admin, require_reseller
from ..models import Subscription, User, Node, SubscriptionNode, NodeStatus, Plan
from ..models_reseller import Reseller, ResellerSubscription
from ..plan_category_models import PlanCategoryAssignment
from ..system_release import ensure_installation_id
from .account_delivery import _share_token, _share_url
from .central_app_v1 import (
    BrandPreviewIn, ProtocolProfilesIn,
    subscription_app_brand_preview, subscription_protocol_catalog,
    subscription_protocol_profiles,
)

router = APIRouter(prefix="/v1/central-app", tags=["central-app-login"])
_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


class AppLoginIn(BaseModel):
    username: str = Field(min_length=6, max_length=120)
    password: str = Field(min_length=8, max_length=256)


class SessionProtocolIn(BaseModel):
    protocol: str = Field(min_length=2, max_length=32)


def _session_subscription(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Subscription:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="APP_SESSION_REQUIRED")
    return verify_app_session(db, authorization[7:].strip())


def _owner_delivery(db: Session, subscription_id: int, reseller_id: int | None) -> Subscription:
    sub = db.get(Subscription, int(subscription_id))
    if sub is None:
        raise HTTPException(status_code=404, detail="SUBSCRIPTION_NOT_FOUND")
    if reseller_id is not None:
        link = db.query(ResellerSubscription).filter(
            ResellerSubscription.subscription_id == sub.id,
            ResellerSubscription.reseller_id == int(reseller_id),
        ).first()
        if link is None:
            raise HTTPException(status_code=404, detail="SUBSCRIPTION_NOT_FOUND")
    return sub


def _deliver(db: Session, sub: Subscription, *, reset: bool) -> JSONResponse:
    if not central_app_entitled():
        raise HTTPException(status_code=403, detail="CENTRAL_APP_NOT_INCLUDED")
    creds = rotate_app_credentials(db, sub) if reset else app_delivery_payload(db, sub)
    if creds is None:
        raise HTTPException(status_code=403, detail="CENTRAL_APP_NOT_INCLUDED")
    db.commit()
    return JSONResponse({
        "subscription_id": int(sub.id),
        "app_username": creds["username"],
        "app_password": creds["password"],
        "subscription_link": _share_url(db, sub),
        "app_password_revision": int(creds["revision"]),
        "vpn_credentials_unchanged": True,
    }, headers=_PRIVATE_HEADERS)


@router.post("/public/login")
def login_app(payload: AppLoginIn, db: Session = Depends(get_db)):
    sub, token = authenticate_app(db, payload.username, payload.password)
    # Server-side share token is used only to project this subscription's
    # existing brand; never requires the app password to equal the VPN password.
    brand = subscription_app_brand_preview(
        BrandPreviewIn(
            account_username=sub.account_username or "",
            share_token=_share_token(sub),
        ),
        db=db,
    )
    return JSONResponse({
        "schema": 1,
        "namespace": subscription_app_namespace(db, sub),
        "session_token": token,
        "account_status": brand.get("account_status"),
        "brand": brand,
    }, headers=_PRIVATE_HEADERS)


@router.get("/session/brand")
def session_brand(
    sub: Subscription = Depends(_session_subscription),
    db: Session = Depends(get_db),
):
    brand = subscription_app_brand_preview(
        BrandPreviewIn(
            account_username=sub.account_username or "",
            share_token=_share_token(sub),
        ), db=db,
    )
    return JSONResponse(brand, headers=_PRIVATE_HEADERS)


@router.get("/session/protocols")
def session_protocols(
    sub: Subscription = Depends(_session_subscription),
    db: Session = Depends(get_db),
):
    response = subscription_protocol_catalog(
        BrandPreviewIn(
            account_username=sub.account_username or "",
            share_token=_share_token(sub),
        ), db=db,
    )
    response.headers.update(_PRIVATE_HEADERS)
    return response


@router.get("/session/plan")
def session_plan(
    sub: Subscription = Depends(_session_subscription),
    db: Session = Depends(get_db),
):
    """Read the panel's two existing plan classifications, not plan-name guesses.

    First dimension is subscription_type (e.g. V2Ray / Premium); second
    dimension is category (the admin-configured user-count group).
    device_limit is a separate numeric entitlement, not a category ID.
    """
    plan = db.get(Plan, int(sub.plan_id))
    if plan is None:
        raise HTTPException(status_code=404, detail="PLAN_NOT_FOUND")
    grouping = db.query(PlanCategoryAssignment).filter(
        PlanCategoryAssignment.plan_id == int(plan.id)
    ).first()
    return JSONResponse({
        "schema": 1,
        "namespace": subscription_app_namespace(db, sub),
        "plan_id": int(plan.id),
        "subscription_type": str(grouping.subscription_type or "اشتراک عمومی")
            if grouping else "اشتراک عمومی",
        "user_count_category": str(grouping.category or "سایر پلن‌ها")
            if grouping else "سایر پلن‌ها",
        "device_limit": int(plan.device_limit if plan.device_limit is not None else 1),
    }, headers=_PRIVATE_HEADERS)


@router.get("/session/account")
def session_account(
    sub: Subscription = Depends(_session_subscription),
    db: Session = Depends(get_db),
):
    """Authenticated subscription-only account snapshot without credentials.

    Zero traffic limit means unlimited. A missing expiry with a configured
    activation duration represents a first-use period not yet started.
    """
    limit = max(0, int(sub.traffic_limit_bytes or 0))
    used = max(0, int(sub.traffic_used_bytes or 0))
    expiry = sub.expires_at
    duration = sub.activation_duration_days
    return JSONResponse({
        "schema": 1,
        "namespace": subscription_app_namespace(db, sub),
        "subscription_id": str(sub.id),
        "traffic_limit_bytes": limit,
        "traffic_used_bytes": used,
        "expires_at": expiry.isoformat() + "Z" if expiry else None,
        "activation_duration_days": int(duration) if duration is not None else None,
        "status": sub.status.value if hasattr(sub.status, "value") else str(sub.status),
    }, headers=_PRIVATE_HEADERS)


@router.get("/session/servers")
def session_servers(
    sub: Subscription = Depends(_session_subscription),
    db: Session = Depends(get_db),
):
    """Current assigned, visible nodes for this one authenticated app account.

    This is an inventory refresh, not a ping or connection success check.
    Never return server credentials, agent URLs, or other customers' nodes.
    """
    nodes = (
        db.query(Node)
        .join(SubscriptionNode, SubscriptionNode.node_id == Node.id)
        .filter(
            SubscriptionNode.subscription_id == sub.id,
            Node.show_to_users.is_(True),
            Node.retired_at.is_(None),
        )
        .order_by(Node.id)
        .limit(500)
        .all()
    )
    return JSONResponse({
        "schema": 1,
        "namespace": subscription_app_namespace(db, sub),
        "servers": [
            {
                "id": str(node.id),
                "name": node.name,
                "country_code": node.country_code,
                "node_online": node.status == NodeStatus.ONLINE,
                "latency_ms": None,
            }
            for node in nodes
        ],
    }, headers=_PRIVATE_HEADERS)


@router.post("/session/profiles")
def session_profiles(
    payload: SessionProtocolIn,
    sub: Subscription = Depends(_session_subscription),
    db: Session = Depends(get_db),
):
    response = subscription_protocol_profiles(
        ProtocolProfilesIn(
            account_username=sub.account_username or "",
            share_token=_share_token(sub),
            protocol=payload.protocol,
        ), db=db,
    )
    response.headers.update(_PRIVATE_HEADERS)
    return response


@router.post("/admin/subscriptions/{subscription_id}/app-delivery")
def admin_app_delivery(
    subscription_id: int, _=Depends(require_admin), db: Session = Depends(get_db),
):
    return _deliver(db, _owner_delivery(db, subscription_id, None), reset=False)


@router.post("/admin/subscriptions/{subscription_id}/app-password-reset")
def admin_app_reset(
    subscription_id: int, _=Depends(require_admin), db: Session = Depends(get_db),
):
    return _deliver(db, _owner_delivery(db, subscription_id, None), reset=True)


@router.post("/customer/subscriptions/{subscription_id}/app-delivery")
def customer_app_delivery(
    subscription_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Only the authenticated subscription owner may retrieve their app login.
    # Do NOT authorize using a share URL or a bare subscription ID.
    sub = db.get(Subscription, int(subscription_id))
    if sub is None or int(sub.user_id) != int(user.id):
        raise HTTPException(status_code=404, detail="SUBSCRIPTION_NOT_FOUND")
    return _deliver(db, sub, reset=False)


@router.post("/reseller/subscriptions/{subscription_id}/app-delivery")
def reseller_app_delivery(
    subscription_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    return _deliver(db, _owner_delivery(db, subscription_id, int(reseller.id)), reset=False)


@router.post("/reseller/subscriptions/{subscription_id}/app-password-reset")
def reseller_app_reset(
    subscription_id: int,
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    return _deliver(db, _owner_delivery(db, subscription_id, int(reseller.id)), reset=True)
