"""Regression checks for renewal coupon checkout wiring."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "app"


def test_renewal_coupon_handlers_and_fsm():
    source = (ROOT / "telegram_runtime_bot.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "discount = State()" in source
    assert 'renewcoupon:enter:' in source
    assert 'renewcoupon:skip:' in source
    assert '@router.message(RenewalPaymentState.discount)' in source
    assert 'f"/v1/discounts/store/orders/{order_id}/apply"' in source
    assert "renewal_payment_methods_keyboard(order_id" in source


def test_discount_scope_uses_real_renewal_relation():
    source = (ROOT / "routers" / "discounts.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "SubscriptionRenewalOrder.order_id == order.id" in source
    assert 'purpose="renewal" if is_renewal else "purchase"' in source
