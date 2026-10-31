from pathlib import Path


def test_main_activates_xray_modern_runtime_before_routes() -> None:
    source = Path("app/main.py").read_text(encoding="utf-8")

    assert "from .xray_modern_runtime import apply_xray_modern_runtime, router as xray_modern_router" in source
    activation = source.index("apply_xray_modern_runtime()")
    subscription_route = source.index("app.include_router(subscription_admin_v2_router, prefix=\"/v1\")")
    account_delivery_route = source.index("app.include_router(account_delivery.router)")

    assert activation < subscription_route
    assert activation < account_delivery_route
