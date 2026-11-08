"""First positive authenticated usage starts configured validity, never invents it."""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.models import Plan
from app.quota_service import _activate_from_accepted_traffic
from app.subscription_override_models import SubscriptionRuntimeOverride


class FakeDB:
    def __init__(self, *, plan=None, override=None):
        self.plan = plan
        self.override = override

    def get(self, model, ident):
        if model is Plan:
            return self.plan
        if model is SubscriptionRuntimeOverride:
            return self.override
        raise AssertionError("unexpected model")


def sub(*, days=None, plan_id=None, starts=None, expires=None):
    return SimpleNamespace(
        id=12, activation_duration_days=days, plan_id=plan_id,
        starts_at=starts, expires_at=expires,
    )


def main():
    t = datetime(2026, 11, 8, 21, 0)
    db = FakeDB()
    s = sub(days=30)
    assert not _activate_from_accepted_traffic(db, s, accepted=0, now=t)
    assert s.starts_at is None and s.expires_at is None
    assert _activate_from_accepted_traffic(db, s, accepted=1024, now=t)
    assert s.starts_at == t and s.expires_at == t + timedelta(days=30)
    assert not _activate_from_accepted_traffic(db, s, accepted=500, now=t + timedelta(hours=2))
    assert s.starts_at == t and s.expires_at == t + timedelta(days=30)

    p = sub(plan_id=5)
    assert _activate_from_accepted_traffic(FakeDB(plan=SimpleNamespace(duration_days=7)), p, accepted=1, now=t)
    assert p.activation_duration_days == 7 and p.expires_at == t + timedelta(days=7)

    legacy = sub()
    assert not _activate_from_accepted_traffic(db, legacy, accepted=100000, now=t)
    assert legacy.starts_at is None and legacy.expires_at is None

    unlimited = sub()
    assert _activate_from_accepted_traffic(
        FakeDB(override=SimpleNamespace(duration_unlimited=True)), unlimited, accepted=1, now=t
    )
    assert unlimited.starts_at == t and unlimited.expires_at is None

    existing_expiry = sub(expires=t + timedelta(days=10))
    assert not _activate_from_accepted_traffic(db, existing_expiry, accepted=1, now=t)
    assert existing_expiry.starts_at is None
    print("FIRST_ACCEPTED_USAGE_VALIDITY_GUARDS_PASS")


if __name__ == "__main__":
    main()
