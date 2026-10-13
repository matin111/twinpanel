from __future__ import annotations

from html import escape

from aiogram import Router

from . import reseller_bot_review
from . import reseller_bot_runtime as legacy_runtime
from .models import Plan
from .reseller_bot_owned_runtime import build_owned_plan_router
from .reseller_owned_plans import owned_plan_by_backing
from .routers import reseller_bot_orders as legacy_orders
from .routers.reseller_bot_orders_owned_v3 import approve_order_owned_v3


_original_build_router = legacy_runtime.build_router
_original_review_caption = reseller_bot_review._review_caption


def _owned_review_caption(db, order):
    text = _original_review_caption(db, order)
    mapping = owned_plan_by_backing(
        db,
        int(order.reseller_id),
        int(order.plan_id),
        active_only=False,
    )
    if not mapping:
        return text

    backing = db.get(Plan, int(order.plan_id))
    internal_name = str(backing.name if backing else "").strip()
    if internal_name:
        text = text.replace(
            escape(internal_name),
            escape(str(mapping.title)),
            1,
        )
    return text


def build_router(reseller_id: int) -> Router:
    parent = Router(name=f"reseller-bot-root-owned-{reseller_id}")
    # Owned-plan handlers are intentionally registered first. The existing
    # router remains behind them for start/dashboard/subscription delivery,
    # receipt recovery, learning center, discounts and legacy compatibility.
    parent.include_router(
        build_owned_plan_router(reseller_id)
    )
    parent.include_router(
        _original_build_router(reseller_id)
    )
    return parent


def install_runtime_overrides() -> None:
    legacy_runtime.build_router = build_router

    # Direct Python callers inside receipt review and legacy wallet code import
    # this symbol at callback time. Point them to the usage-pool aware approval.
    legacy_orders.approve_order = approve_order_owned_v3

    # Keep internal backing plan ids/names out of reseller-owner receipt texts.
    reseller_bot_review._review_caption = _owned_review_caption


def main() -> None:
    install_runtime_overrides()
    legacy_runtime.main()


if __name__ == "__main__":
    main()
