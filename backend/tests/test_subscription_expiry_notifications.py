from datetime import datetime, timedelta

from app.subscription_expiry_notifications import _dedupe_stage, _stage
from app.user_notification_models import SubscriptionExpiryNotificationClaim


def test_expiry_reminder_stages_cover_three_two_one_and_expiry_day():
    now = datetime(2026, 11, 3, 12, 0, 0)

    assert _stage(now + timedelta(days=4), now) is None
    assert _stage(now + timedelta(days=3), now) == "3d"
    assert _stage(now + timedelta(days=2), now) == "2d"
    assert _stage(now + timedelta(days=1), now) == "1d"
    assert _stage(now, now) == "0d"
    assert _stage(now - timedelta(minutes=1), now) == "0d"


def test_expiry_day_keeps_legacy_dedupe_token():
    assert _dedupe_stage("0d") == "expired"
    assert _dedupe_stage("1d") == "1d"
    assert _dedupe_stage("2d") == "2d"
    assert _dedupe_stage("3d") == "3d"


def test_expiry_claim_event_key_is_database_unique():
    event_key = SubscriptionExpiryNotificationClaim.__table__.c.event_key

    assert event_key.unique is True
    assert event_key.nullable is False
