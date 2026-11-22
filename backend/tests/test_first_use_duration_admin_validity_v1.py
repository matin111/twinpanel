"""Regression checks: days added to an unstarted account do not start its clock."""
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import importlib.util


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "subscription_validity_v1",
    ROOT / "app/services/subscription_validity_v1.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_waiting_finite_add_days_keeps_dates_empty():
    sub = SimpleNamespace(starts_at=None, expires_at=None, activation_duration_days=30)
    override = SimpleNamespace(duration_unlimited=False)
    module.add_validity_days(sub, 10, datetime(2026, 11, 22), override=override)
    assert sub.activation_duration_days == 40
    assert sub.starts_at is None and sub.expires_at is None


def test_waiting_unlimited_add_days_keeps_dates_empty():
    sub = SimpleNamespace(starts_at=None, expires_at=None, activation_duration_days=0)
    override = SimpleNamespace(duration_unlimited=True)
    module.add_validity_days(sub, 90, datetime(2026, 11, 22), override=override)
    assert sub.activation_duration_days == 90
    assert sub.starts_at is None and sub.expires_at is None
    assert override.duration_unlimited is False


def test_started_expiry_extends_from_later_of_now_and_expiry():
    now = datetime(2026, 11, 22)
    sub = SimpleNamespace(starts_at=now - timedelta(days=5), expires_at=now + timedelta(days=25), activation_duration_days=30)
    module.add_validity_days(sub, 10, now)
    assert sub.expires_at == now + timedelta(days=35)


def test_admin_edit_respects_unstarted_finite_account():
    source = (ROOT / "app/routers/subscription_admin_edit_fast_v1.py").read_text()
    assert "if not expiry_sent and sub.starts_at is None and sub.expires_at is None:" in source
    assert "sub.activation_duration_days = new_duration_days" in source


if __name__ == "__main__":
    for name, fn in sorted(globals().copy().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
