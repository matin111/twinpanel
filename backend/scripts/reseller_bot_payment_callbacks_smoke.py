from __future__ import annotations

import inspect

from app.reseller_bot_payment_runtime import build_owned_payment_router
from app.reseller_bot_runtime_owned import build_router


def main() -> None:
    payment_source = inspect.getsource(build_owned_payment_router)
    root_source = inspect.getsource(build_router)

    assert 'F.data.startswith("rpay:")' in payment_source
    assert 'F.data.startswith("rwallet:")' in payment_source
    assert 'callback_data=f"rwalletpay:{int(order.id)}"' in payment_source
    assert "build_owned_payment_router(reseller_id)" in root_source
    assert root_source.index("build_owned_payment_router") < root_source.index(
        "build_owned_plan_router"
    )

    router = build_owned_payment_router(1)
    assert router.name == "reseller-owned-payment-1"
    assert len(router.callback_query.handlers) >= 2

    print("RESELLER_BOT_PAYMENT_CALLBACKS_OK")


if __name__ == "__main__":
    main()
