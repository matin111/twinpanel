"""Regression tests for timestamp-aware card SMS approval (no production DB needed)."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
READER_PATH = ROOT / "backend/app/routers/wallet_sms_reader.py"
DASHBOARD_PATH = ROOT / "backend/app/routers/sms_reader_dashboard.py"
reader_source = READER_PATH.read_text(encoding="utf-8")
dashboard_source = DASHBOARD_PATH.read_text(encoding="utf-8")
compile(reader_source, str(READER_PATH), "exec")
compile(dashboard_source, str(DASHBOARD_PATH), "exec")


def _window(now: datetime, received: datetime):
    """Execute the actual helper in isolation, avoiding DB and network imports."""
    tree = ast.parse(reader_source)
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_sms_match_window"
    )
    isolated = ast.Module(body=[helper], type_ignores=[])
    ast.fix_missing_locations(isolated)
    namespace = {"datetime": datetime, "timedelta": timedelta}
    exec(compile(isolated, str(READER_PATH), "exec"), namespace)
    return namespace["_sms_match_window"](now, received)


def test_fresh_sms_can_match_order_created_before_deposit():
    now = datetime(2026, 11, 4, 10, 0)
    start, end = _window(now, now - timedelta(minutes=8))
    assert start <= now - timedelta(minutes=20) <= end
    assert end == now - timedelta(minutes=6)


def test_old_deposit_cannot_pay_new_order_even_when_reader_was_delayed():
    now = datetime(2026, 11, 4, 10, 0)
    start, end = _window(now, now - timedelta(minutes=30))
    assert not (start <= now - timedelta(minutes=5) <= end)


def test_stale_and_future_sms_go_to_review_not_automatic_approval():
    now = datetime(2026, 11, 4, 10, 0)
    assert _window(now, now - timedelta(hours=4)) is None
    assert _window(now, now + timedelta(minutes=6)) is None


def test_missing_timestamp_fallback_matches_current_pending_order():
    now = datetime(2026, 11, 4, 10, 0)
    start, end = _window(now, now)
    assert start <= now - timedelta(minutes=1) <= end
    assert end == now


def test_match_requires_exactly_one_payment_or_wallet_candidate():
    assert "if total_matches != 1:" in reader_source
    assert 'event.status = "ambiguous" if total_matches > 1 else "unmatched"' in reader_source
    assert "PaymentIntent.payable_amount_toman == amount" in reader_source
    assert "CustomerWalletTopup.payable_amount_toman == amount" in reader_source
    assert "PaymentIntent.created_at <= latest" in reader_source
    assert "CustomerWalletTopup.created_at <= latest" in reader_source
    assert 'event.status = "outside_verification_window"' in reader_source


def test_sms_dashboard_get_never_enables_verification_on_its_own():
    assert "cfg.sms_auto_verify = True" not in dashboard_source
    assert "cfg.sms_reader_enabled = True" not in dashboard_source
    assert "db.commit()" not in dashboard_source
