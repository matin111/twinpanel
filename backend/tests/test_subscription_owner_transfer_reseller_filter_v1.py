"""Real ownership transfer and reseller pagination regression coverage."""
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Node, Plan, ProtocolCredential, Subscription, SubscriptionNode,
    SubscriptionProtocol, SubscriptionStatus, User, UserRole,
)
from app.models_reseller import Reseller, ResellerCustomer, ResellerSubscription
from app.subscription_override_models import SubscriptionRuntimeOverride
from app.routers.reseller_admin_v2 import (
    SubscriptionTransferIn, transfer_subscription_to_reseller,
)
from app.routers.subscription_admin_v2 import (
    SubscriptionOwnerTransferIn, transfer_subscription_to_user, admin_page_v3,
)


def sample_db():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[
        User.__table__, Plan.__table__, Node.__table__,
        Subscription.__table__, SubscriptionNode.__table__,
        SubscriptionProtocol.__table__, ProtocolCredential.__table__,
        Reseller.__table__, ResellerCustomer.__table__,
        ResellerSubscription.__table__, SubscriptionRuntimeOverride.__table__,
    ])
    db = Session(engine)
    db.add_all([
        User(id=1, email="admin@example.test", full_name="Administrator",
             password_hash="x", role=UserRole.ADMIN, is_active=True),
        User(id=2, email="customer@example.test", full_name="Destination",
             password_hash="x", role=UserRole.USER, is_active=True),
        User(id=3, email="reseller@example.test", full_name="Reseller",
             password_hash="x", role=UserRole.USER, is_active=True),
        User(id=4, email="direct@example.test", full_name="Direct User",
             password_hash="x", role=UserRole.USER, is_active=True),
        Plan(id=10, name="Test", duration_days=30, traffic_gb=100,
             device_limit=1, price_toman=0),
        Reseller(id=3, owner_user_id=3, code="RESELLER3", name="Example reseller",
                 is_active=True, reseller_tier="premium_static_ip"),
        ResellerCustomer(reseller_id=3, user_id=2),
        Subscription(id=2816, user_id=1, plan_id=10,
                     status=SubscriptionStatus.ACTIVE, traffic_limit_bytes=90,
                     traffic_used_bytes=22, share_code="test-sub-link"),
        Subscription(id=257, user_id=1, plan_id=10,
                     status=SubscriptionStatus.ACTIVE, traffic_limit_bytes=25,
                     traffic_used_bytes=1),
    ])
    db.commit()
    return engine, db


def test_reseller_transfer_updates_actual_owner_without_vpn_mutation():
    engine, db = sample_db()
    try:
        original = db.get(Subscription, 2816)
        before = (original.traffic_limit_bytes, original.traffic_used_bytes,
                  original.share_code, original.status, original.plan_id)
        first = transfer_subscription_to_reseller(
            3, 2816, SubscriptionTransferIn(customer_user_id=2), db)
        assert first["owner_user_id"] == 2
        db.expire_all()
        sub = db.get(Subscription, 2816)
        assert sub.user_id == 2
        assert (sub.traffic_limit_bytes, sub.traffic_used_bytes,
                sub.share_code, sub.status, sub.plan_id) == before
        link = db.query(ResellerSubscription).filter_by(subscription_id=2816).one()
        assert (link.reseller_id, link.customer_user_id) == (3, 2)
        second = transfer_subscription_to_reseller(
            3, 2816, SubscriptionTransferIn(customer_user_id=2), db)
        assert second["already_transferred"] is True
    finally:
        db.close()
        engine.dispose()


def test_old_management_only_transfer_repairs_stale_administrator_owner():
    engine, db = sample_db()
    try:
        db.add(ResellerSubscription(id=17, reseller_id=3, subscription_id=2816,
                                    customer_user_id=2, buy_price_toman=0,
                                    sell_price_toman=0))
        db.commit()
        result = transfer_subscription_to_reseller(
            3, 2816, SubscriptionTransferIn(customer_user_id=2), db)
        assert result["owner_user_id"] == 2
        assert db.get(Subscription, 2816).user_id == 2
    finally:
        db.close()
        engine.dispose()


def test_direct_user_transfer_detaches_free_reseller_mapping():
    engine, db = sample_db()
    try:
        transfer_subscription_to_reseller(
            3, 2816, SubscriptionTransferIn(customer_user_id=2), db)
        response = transfer_subscription_to_user(
            2816, SubscriptionOwnerTransferIn(user_id=4), db)
        assert response["reseller_id"] is None
        assert db.get(Subscription, 2816).user_id == 4
        assert db.query(ResellerSubscription).filter_by(subscription_id=2816).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_paid_reseller_sale_cannot_be_silently_detached():
    engine, db = sample_db()
    try:
        db.add(ResellerSubscription(id=17, reseller_id=3, subscription_id=2816,
                                    customer_user_id=2, buy_price_toman=100,
                                    sell_price_toman=200))
        db.commit()
        with pytest.raises(HTTPException) as error:
            transfer_subscription_to_user(
                2816, SubscriptionOwnerTransferIn(user_id=4), db)
        assert error.value.status_code == 409
        assert db.get(Subscription, 2816).user_id == 1
    finally:
        db.close()
        engine.dispose()


def test_reseller_filter_is_database_side_before_pagination():
    engine, db = sample_db()
    try:
        transfer_subscription_to_reseller(
            3, 2816, SubscriptionTransferIn(customer_user_id=2), db)
        with patch("app.routers.subscription_admin_v2._online_subscription_ids",
                   return_value=set()):
            owned = admin_page_v3(limit=1, offset=0, status="all",
                                  reseller_id=3, db=db)
            direct = admin_page_v3(limit=1, offset=0, status="all",
                                   reseller_id=-1, db=db)
        assert owned["total"] == 1
        assert owned["items"][0]["id"] == 2816
        assert owned["items"][0]["user_id"] == 2
        assert owned["items"][0]["reseller_name"] == "Example reseller"
        assert direct["total"] == 1
        assert direct["items"][0]["id"] == 257
        assert owned["stats"]["total"] == direct["stats"]["total"] == 2
    finally:
        db.close()
        engine.dispose()
