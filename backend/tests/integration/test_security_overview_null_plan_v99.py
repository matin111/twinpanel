from types import SimpleNamespace

from app.models import Plan, Subscription, User
from app.quota_models import QuotaDevice, QuotaSession, QuotaUsageEvent
from app.routers.admin import security_overview


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(self):
        self.subscription = SimpleNamespace(
            id=2,
            user_id=12,
            plan_id=None,
            status="active",
            traffic_used_bytes=0,
            traffic_limit_bytes=0,
        )
        self.user = SimpleNamespace(
            id=12,
            full_name="Legacy User",
            email="legacy@example.com",
        )

    def query(self, model):
        if model is Subscription:
            return FakeQuery([self.subscription])
        if model is User:
            return FakeQuery([self.user])
        if model is Plan:
            raise AssertionError(
                "Plan query must be skipped when every plan_id is NULL"
            )
        if model in (QuotaSession, QuotaDevice, QuotaUsageEvent):
            return FakeQuery([])
        raise AssertionError(f"unexpected query model: {model!r}")


def test_security_overview_accepts_subscription_without_plan():
    payload = security_overview(db=FakeDB())

    assert payload["summary"]["subscriptions"] == 1
    assert len(payload["items"]) == 1

    item = payload["items"][0]
    assert item["subscription_id"] == 2
    assert item["user_id"] == 12
    assert item["plan_name"] == ""
    assert item["device_limit"] == 1
    assert item["risk_level"] == "normal"


if __name__ == "__main__":
    test_security_overview_accepts_subscription_without_plan()
    print("SECURITY_OVERVIEW_NULL_PLAN_V99_OK")
