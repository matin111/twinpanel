"""Unlimited time and unlimited traffic are orthogonal. No production DB calls."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.models import Plan, SubscriptionStatus
from app.quota_models import QuotaDevice
from app.quota_schemas import SessionOpenIn
from app.quota_service import _activate_from_accepted_traffic
from app.quota_service_v2 import open_session
from app.subscription_override_models import (
    SubscriptionRuntimeOverride,
    classify_time_policy,
    has_verified_unlimited_time,
)


def make_subscription(*, days=0, limit=1000, used=0,
                      started=None, expiry=None):
    return SimpleNamespace(
        id=42,plan_id=None,status=SubscriptionStatus.ACTIVE,
        starts_at=started,expires_at=expiry,activation_duration_days=days,
        traffic_limit_bytes=limit,traffic_used_bytes=used,
    )


def make_db(subscription, override=None):
    db=MagicMock()
    device=SimpleNamespace(id=7,subscription_id=42,status="active",protocol="wireguard")
    db.scalar.side_effect=[None,subscription,0]
    def get(model, ident):
        if model is QuotaDevice:
            return device
        if model is SubscriptionRuntimeOverride:
            return override
        if model is Plan:
            return None
        raise AssertionError("unrecognized model "+str(model))
    db.get.side_effect=get
    return db


class UnlimitedTimeQuotaTests(TestCase):
    def setUp(self):
        self.data=SessionOpenIn(
            session_key="test-fresh-session-1",subscription_id=42,
            device_id=7,protocol="wireguard"
        )

    def open(self,subscription,override=None):
        db=make_db(subscription,override)
        with patch("app.quota_service_v2._lock"):
            result=open_session(db,1,self.data)
        return result,db

    def test_explicit_unlimited_time_with_finite_traffic(self):
        sub=make_subscription(limit=1000,used=200)
        override=SimpleNamespace(duration_unlimited=True,device_limit=2)
        result,db=self.open(sub,override)
        self.assertIsNotNone(sub.starts_at)
        self.assertIsNone(sub.expires_at)
        self.assertTrue(result["duration_unlimited_verified"])
        self.assertFalse(result["traffic_unlimited"])
        self.assertEqual(result["time_policy_state"],"explicit_unlimited")
        db.add.assert_called_once()

    def test_limited_time_with_unlimited_traffic(self):
        sub=make_subscription(days=30,limit=0,used=999999)
        override=SimpleNamespace(duration_unlimited=False,device_limit=2)
        result,_=self.open(sub,override)
        self.assertEqual(sub.expires_at,sub.starts_at+timedelta(days=30))
        self.assertTrue(result["traffic_unlimited"])
        self.assertFalse(result["duration_unlimited_verified"])

    def test_both_unlimited(self):
        sub=make_subscription(limit=0,used=0)
        result,_=self.open(sub,SimpleNamespace(duration_unlimited=True,device_limit=2))
        self.assertTrue(result["traffic_unlimited"])
        self.assertTrue(result["duration_unlimited_verified"])
        self.assertIsNone(sub.expires_at)

    def test_unlimited_time_does_not_bypass_finite_volume(self):
        sub=make_subscription(limit=1000,used=1000)
        db=make_db(sub,SimpleNamespace(duration_unlimited=True,device_limit=2))
        with patch("app.quota_service_v2._lock"):
            with self.assertRaises(HTTPException) as ctx:
                open_session(db,1,self.data)
        self.assertEqual(ctx.exception.status_code,403)
        self.assertEqual(ctx.exception.detail,"subscription_quota_exhausted")
        self.assertIsNone(sub.starts_at)
        db.add.assert_not_called()

    def test_unknown_legacy_keeps_existing_admission_but_does_not_get_fake_first_use(self):
        sub=make_subscription(days=None)
        result,_=self.open(sub,None)
        self.assertIsNone(sub.starts_at)
        self.assertIsNone(sub.expires_at)
        self.assertEqual(result["time_policy_state"],"legacy_unknown_duration")
        self.assertFalse(result["duration_unlimited_verified"])

    def test_positive_usage_of_unknown_legacy_does_not_fabricate_start_or_expiry(self):
        sub=make_subscription(days=None)
        db=make_db(sub,None)
        self.assertFalse(_activate_from_accepted_traffic(
            db,sub,accepted=500,now=datetime(2026,11,26)))
        self.assertIsNone(sub.starts_at)
        self.assertIsNone(sub.expires_at)

    def test_accepted_positive_usage_starts_explicit_unlimited_without_expiry(self):
        sub=make_subscription()
        db=make_db(sub,SimpleNamespace(duration_unlimited=True,device_limit=1))
        t=datetime(2026,11,26)
        self.assertFalse(_activate_from_accepted_traffic(db,sub,accepted=0,now=t))
        self.assertTrue(_activate_from_accepted_traffic(db,sub,accepted=100,now=t))
        self.assertEqual(sub.starts_at,t)
        self.assertIsNone(sub.expires_at)
        self.assertFalse(_activate_from_accepted_traffic(
            db,sub,accepted=20,now=t+timedelta(days=2)))
        self.assertEqual(sub.starts_at,t)

    def test_stale_unlimited_flag_does_not_override_real_expiry(self):
        sub=make_subscription(expiry=datetime(2026,11,25))
        override=SimpleNamespace(duration_unlimited=True,device_limit=1)
        self.assertEqual(classify_time_policy(sub,None,override),"finite_explicit_expiry")
        self.assertFalse(has_verified_unlimited_time(sub,None,override))
        db=make_db(sub,override)
        with patch("app.quota_service_v2._lock"):
            with self.assertRaises(HTTPException) as ctx:
                open_session(db,1,self.data)
        self.assertEqual(ctx.exception.detail,"subscription_expired")
        db.add.assert_not_called()

    def test_finite_waiting_first_use_stays_date_free_until_first_real_usage(self):
        sub=make_subscription(days=90,limit=2000,used=0)
        db=make_db(sub,None)
        self.assertEqual(classify_time_policy(sub),"finite_waiting_first_use")
        self.assertFalse(_activate_from_accepted_traffic(
            db,sub,accepted=0,now=datetime(2026,11,26)))
        self.assertIsNone(sub.starts_at)
        t=datetime(2026,11,26)
        self.assertTrue(_activate_from_accepted_traffic(db,sub,accepted=1,now=t))
        self.assertEqual(sub.expires_at,t+timedelta(days=90))


if __name__=="__main__":
    main()
