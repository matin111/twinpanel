import ast
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _plan_terms_function():
    """Load only the Store entitlement helper without importing the app.

    Importing app.routers.store loads runtime settings and a database engine,
    which is unrelated to this regression contract. Executing just the parsed
    helper keeps this smoke deterministic while still testing the committed
    implementation rather than a copied test function.
    """
    source = _source("app/routers/store.py")
    tree = ast.parse(source, filename="app/routers/store.py")
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_plan_subscription_terms"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "Plan": object,
        "HTTPException": HTTPException,
    }
    exec(
        compile(module, "app/routers/store.py", "exec"),
        namespace,
    )
    return namespace["_plan_subscription_terms"]


def main() -> None:
    plan_terms = _plan_terms_function()

    # Central Store: finite plans must stay finite; 0 GB remains the explicit
    # legacy unlimited-plan contract.
    assert plan_terms(
        SimpleNamespace(traffic_gb=50, duration_days=30)
    ) == (50, 30)
    assert plan_terms(
        SimpleNamespace(traffic_gb=0, duration_days=30)
    ) == (None, 30)

    try:
        plan_terms(
            SimpleNamespace(traffic_gb=50, duration_days=0)
        )
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("invalid plan duration was accepted")

    store = _source("app/routers/store.py")
    assert "traffic_gb, duration_days = (" in store
    assert "_plan_subscription_terms(plan)" in store
    assert "traffic_gb=traffic_gb" in store
    assert "duration_days=duration_days" in store

    # Main sales bot uses the exact Store order pipeline, so the same finite
    # plan terms reach customer-panel checkout and Telegram checkout.
    main_bot = _source("app/telegram_purchase_bot.py")
    assert '"/v1/store/orders"' in main_bot
    assert '"plan_id": plan_id' in main_bot

    # The production reseller supervisor replaces the legacy approval callback
    # with owned_v3. New reseller orders therefore keep their immutable order
    # snapshot instead of inheriting central Store behavior accidentally.
    reseller_runtime = _source("app/reseller_bot_runtime_owned.py")
    assert "legacy_orders.approve_order = approve_order_owned_v3" in reseller_runtime

    payment_runtime = _source("app/reseller_bot_payment_runtime.py")
    assert "traffic_gb=int(plan.traffic_gb)" in payment_runtime
    assert "duration_days=int(plan.duration_days)" in payment_runtime

    owned_runtime = _source("app/reseller_bot_owned_runtime.py")
    assert "traffic_gb=int(row.traffic_gb)" in owned_runtime
    assert "duration_days=int(row.duration_days)" in owned_runtime

    owned_v3 = _source("app/routers/reseller_bot_orders_owned_v3.py")
    assert "traffic_gb=int(row.traffic_gb)" in owned_v3
    assert "duration_days=int(row.duration_days)" in owned_v3
    assert "create_subscription_from_owned_plan(" in owned_v3

    owned_plans = _source("app/reseller_owned_plans.py")
    assert "traffic_bytes=int(reseller_plan.traffic_gb) * GB" in owned_plans
    assert "duration_days=int(reseller_plan.duration_days)" in owned_plans

    order_model = _source("app/reseller_bot_order_models.py")
    assert "traffic_gb: Mapped[int]" in order_model
    assert "duration_days: Mapped[int]" in order_model
    assert "nullable=False" in order_model

    print("PURCHASE_ENTITLEMENT_REGRESSION_OK")


if __name__ == "__main__":
    main()
