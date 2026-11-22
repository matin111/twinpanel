"""Imported subscription renewal checkout must expose the ordinary coupon step."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"


def _handler_body(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    node = next(
        n for n in ast.walk(module)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return ast.get_source_segment(source, node)


def test_imported_renewal_offers_coupon_before_payment():
    body = _handler_body(
        ROOT / "telegram_subscription_import_bot_v1.py",
        "import_renewal_order",
    )
    assert 'callback_data=f"renewcoupon:enter:{order_id}"' in body
    assert 'callback_data=f"renewcoupon:skip:{order_id}"' in body
    assert '"کد تخفیف دارید؟"' in body
    assert 'callback_data=f"renewpay:' not in body
    assert 'callback_data=f"renewwallet:' not in body


def test_shared_coupon_handler_supports_imported_payer_orders():
    body = (ROOT / "telegram_runtime_bot.py").read_text(encoding="utf-8")
    ast.parse(body)
    assert 'F.data.startswith("renewcoupon:enter:")' in body
    assert 'F.data.startswith("renewcoupon:skip:")' in body
    assert 'f"/v1/discounts/store/orders/{order_id}/apply"' in body
    assert 'request("GET", "/v1/store/orders/me", token=token)' in body


def test_imported_order_uses_renewal_relation():
    source = (ROOT / "routers" / "telegram_subscription_import_v1.py").read_text(encoding="utf-8")
    assert 'SubscriptionRenewalOrder(' in source
    discounts = (ROOT / "routers" / "discounts.py").read_text(encoding="utf-8")
    assert "SubscriptionRenewalOrder.order_id == order.id" in discounts
    assert 'purpose="renewal" if is_renewal else "purchase"' in discounts
