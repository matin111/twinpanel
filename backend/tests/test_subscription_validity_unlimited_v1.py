"""No-database regression tests for unlimited and dated account lifetimes."""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
package = types.ModuleType("app")
package.__path__ = [str(root / "app")]
sys.modules["app"] = package

from app.subscription_override_models import duration_is_unlimited, unlimited_without_expiry
from app.services.subscription_validity_v1 import add_validity_days


class FakeDb:
    def __init__(self, override=None, plan=None):
        self.override = override
        self.plan = plan

    def get(self, model, _id):
        if model.__name__ == "SubscriptionRuntimeOverride":
            return self.override
        if model.__name__ == "Plan":
            return self.plan
        return None


def sub(days=0, expires=None, started=None, plan_id=None):
    return SimpleNamespace(
        id=123,
        plan_id=plan_id,
        starts_at=started,
        expires_at=expires,
        activation_duration_days=days,
    )


def run():
    now = datetime(2026, 11, 10, 12, 0)
    open_ended = sub()
    override = SimpleNamespace(duration_unlimited=True)
    assert duration_is_unlimited(FakeDb(), open_ended)
    assert duration_is_unlimited(FakeDb(override=override), open_ended)

    add_validity_days(open_ended, 30, now, override=override)
    assert open_ended.starts_at == now
    assert open_ended.expires_at == now + timedelta(days=30)
    assert open_ended.activation_duration_days == 30
    assert not override.duration_unlimited
    assert not duration_is_unlimited(FakeDb(override=override), open_ended)
    print("UNLIMITED_TO_DATED_30_DAYS_PASS")

    # A stale override must never obscure an authoritative expiry timestamp.
    override.duration_unlimited = True
    assert not unlimited_without_expiry(open_ended, override=override)
    assert not duration_is_unlimited(FakeDb(override=override), open_ended)
    print("EXPLICIT_EXPIRY_WINS_PASS")

    pending = sub(days=12)
    add_validity_days(pending, 5, now)
    assert pending.activation_duration_days == 17
    assert pending.expires_at is None
    assert pending.starts_at is None
    print("FINITE_FIRST_CONNECTION_START_PRESERVED_PASS")

    plan = SimpleNamespace(duration_days=15)
    inherited = sub(plan_id=7)
    assert not duration_is_unlimited(FakeDb(plan=plan), inherited)
    add_validity_days(inherited, 5, now, plan_days=plan.duration_days)
    assert inherited.activation_duration_days == 20
    assert inherited.expires_at is None
    print("PLAN_DURATION_FALLBACK_PASS")

    expired = sub(days=10, started=now-timedelta(days=30), expires=now-timedelta(days=20))
    add_validity_days(expired, 7, now)
    assert expired.expires_at == now+timedelta(days=7)
    assert expired.activation_duration_days == 17
    print("EXPIRED_DATE_EXTENDS_FROM_TODAY_PASS")

    flagged = SimpleNamespace(duration_unlimited=True)
    previously_active = sub(days=0, started=now-timedelta(days=80))
    add_validity_days(previously_active, 14, now, override=flagged)
    assert previously_active.starts_at == now
    assert previously_active.expires_at == now+timedelta(days=14)
    assert not flagged.duration_unlimited
    print("STARTED_INDEFINITE_ACCOUNT_CONVERTS_PASS")

    reset = sub(days=30, started=now-timedelta(days=8), expires=now+timedelta(days=22))
    add_validity_days(reset, 10, now, reset_date=True)
    assert reset.expires_at == now+timedelta(days=10)
    assert reset.activation_duration_days == 10
    print("DATE_RESET_STARTS_NEW_TERM_PASS")


if __name__ == "__main__":
    run()
