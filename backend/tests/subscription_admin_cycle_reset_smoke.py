"""Regression: admin renewal/edit usage reset preserves immutable quota history.

Run: PYTHONPATH=backend python backend/tests/subscription_admin_cycle_reset_smoke.py
No database writes, subscriptions, node counters or external services are used.
"""
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.models import SubscriptionStatus

from fastapi import HTTPException

from app.routers.account_delivery import extend_subscription_v17
from app.services.subscription_cycle_reset_v1 import reset_subscription_period_usage
from app.quota_models import QuotaAuditLog


class Query:
    def __init__(self, db):
        self.db = db

    def filter(self, *args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.db.sub


class DB:
    def __init__(self, subscription):
        self.sub = subscription
        self.events = []
        self.commits = 0

    def query(self, model):
        return Query(self)

    def get(self, model, ident):
        return self.sub if int(ident) == self.sub.id else None

    def add(self, item):
        self.events.append(item)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        return None


def check():
    sub = SimpleNamespace(
        id=9333, traffic_used_bytes=800000000,
        traffic_limit_bytes=2 * 1024**3,
        starts_at=datetime.utcnow() - timedelta(days=15),
        expires_at=datetime.utcnow() + timedelta(days=15),
        activation_duration_days=30, plan_id=None,
        status=SubscriptionStatus.ACTIVE,
    )
    db = DB(sub)
    first_expiry = sub.expires_at
    first_limit = sub.traffic_limit_bytes

    result = extend_subscription_v17(9333, {"add_days": 0, "add_traffic_gb": 0, "reset_usage": True}, db)
    assert result["reset_usage"] is True and result["reset_date"] is False
    assert sub.traffic_used_bytes == 0 and sub.traffic_limit_bytes == first_limit
    assert sub.expires_at == first_expiry
    assert len(db.events) == 1 and isinstance(db.events[0], QuotaAuditLog)
    assert db.events[0].details["previous_usage_bytes"] == 800000000
    assert db.events[0].details["preserves_node_cursors"] is True
    assert db.events[0].details["preserves_historical_usage_events"] is True

    before = datetime.utcnow()
    result = extend_subscription_v17(9333, {"add_days": 30, "add_traffic_gb": 3, "reset_date": True}, db)
    assert result["reset_date"] and not result["reset_usage"]
    assert before <= sub.starts_at <= datetime.utcnow()
    assert sub.expires_at == sub.starts_at + timedelta(days=30)
    assert sub.traffic_limit_bytes == first_limit + 3*1024**3
    assert len(db.events) == 1

    previous = sub.expires_at
    extend_subscription_v17(9333, {"add_days": 2}, db)
    assert sub.expires_at == previous + timedelta(days=2)
    for invalid in (
        {"reset_date": True, "add_days": 0},
        {"reset_date": True, "add_days": -1},
        {"add_days": -20},
        {},
    ):
        try:
            extend_subscription_v17(9333, invalid, db)
            assert False, f"Accepted invalid {invalid!r}"
        except HTTPException as exc:
            assert exc.status_code == 422

    other = SimpleNamespace(id=33, traffic_used_bytes=123456)
    db2=DB(other)
    old = reset_subscription_period_usage(db2, other, origin="admin_edit")
    assert old == 123456 and other.traffic_used_bytes == 0
    assert db2.events[0].action == "subscription_usage_period_reset"
    assert db2.events[0].details["origin"] == "admin_edit"

    # Prior quota exhaustion may be restored; unrelated manual suspension
    # must never be silently lifted.
    from app.services import subscription_cycle_reset_v1 as service
    sub.status = SubscriptionStatus.SUSPENDED
    sub.traffic_limit_bytes = 1024
    sub.traffic_used_bytes = 1024
    sub.expires_at = datetime.utcnow() + timedelta(days=2)
    with patch.object(service, "queue_subscription_enforcement") as restored:
        extend_subscription_v17(9333, {"reset_usage": True}, db)
        assert sub.status == SubscriptionStatus.ACTIVE
        restored.assert_called_once()
        assert restored.call_args.kwargs["command_type"] == "restore_subscription"
        sub.status = SubscriptionStatus.SUSPENDED
        sub.traffic_used_bytes = 1
        extend_subscription_v17(9333, {"reset_usage": True}, db)
        assert sub.status == SubscriptionStatus.SUSPENDED
        assert restored.call_count == 1

    root=Path(__file__).resolve().parents[1]
    fast=(root/"app/routers/subscription_admin_edit_fast_v1.py").read_text()
    ui=(root.parent/"components/legacy-subscriptions-exact.tsx").read_text()
    assert 'reset_subscription_period_usage(db, sub, origin="admin_edit")' in fast
    assert "reset_usage:editResetUsage" in ui
    assert "reset_usage:extendResetUsage,reset_date:extendResetDate" in ui
    assert "setExtendResetUsage(false)" in ui and "setExtendResetDate(false)" in ui
    print("SUBSCRIPTION_ADMIN_CYCLE_RESET_SMOKE_PASS")


if __name__ == "__main__":
    check()
