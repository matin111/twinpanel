from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "app" / "routers" / "subscriptions.py"


def test_admin_subscription_list_uses_bulk_helpers() -> None:
    text = PATH.read_text(encoding="utf-8")
    assert "def subscription_out_from_maps(" in text
    assert "def _bulk_subscription_context(" in text
    assert "return [subscription_out_from_maps(sub, context) for sub in rows]" in text


def test_subscription_out_does_not_lookup_null_plan() -> None:
    text = PATH.read_text(encoding="utf-8")
    assert "plan = db.get(Plan, sub.plan_id) if sub.plan_id is not None else None" in text


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("subscriptions_bulk_smoke: passed")
