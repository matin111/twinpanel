from __future__ import annotations

import sys
from typing import Any

from . import telegram_notify_service
from .protocol_account_registry import (
    ALL_PROTOCOL_KEYS,
    PROTOCOL_TITLES,
    normalize_protocols,
)


# TWINPANEL_TELEGRAM_PURCHASE_DELIVERY_FIX_V1
#
# The Telegram purchase router historically derived protocols from five legacy
# boolean Plan columns. The public /v1/plans payload now exposes the canonical
# PlanProtocol snapshot through ``protocols`` and may contain all 15 protocols.
# Use that canonical list for both rendering and order creation.
#
# Payment fulfillment is also intentionally idempotent at the notification
# boundary. Several historical approval/recovery paths still enqueue
# ``payment_approved`` with an old event-key shape. Canonicalize every such
# event to the same order/payment/subscription key so multiple producers cannot
# create duplicate Telegram delivery rows.
#
# TWINPANEL_MAIN_BOT_PARTIAL_DELIVERY_RECOVERY_V2
# Paid orders must not lose Telegram delivery merely because one protocol has a
# transient provisioning failure. Once the subscription already has a valid
# subscription link plus at least one usable credential/account identity, it is
# customer-deliverable. Mark the order fulfilled and let background convergence
# complete any remaining protocol on the same subscription link.


LEGACY_PLAN_FIELDS = {
    "cisco": "enable_cisco",
    "openvpn": "enable_openvpn",
    "wireguard": "enable_wireguard",
    "l2tp": "enable_l2tp",
    "v2ray": "enable_v2ray",
}

_ORIGINAL_QUEUE = None
_ORIGINAL_FULFILL = None
_INSTALLED = False


def canonical_plan_protocols(plan: dict[str, Any] | None) -> list[str]:
    plan = plan or {}

    raw = plan.get("protocols")
    if isinstance(raw, list):
        try:
            values = normalize_protocols(raw)
        except (TypeError, ValueError):
            values = []
        if values:
            return values

    # Migration-safe fallback for old API payloads which only exposed the five
    # classic boolean fields.
    return [
        protocol
        for protocol, field in LEGACY_PLAN_FIELDS.items()
        if bool(plan.get(field))
    ]


def canonical_protocol_text(plan: dict[str, Any] | None) -> str:
    values = canonical_plan_protocols(plan)
    return " • ".join(
        PROTOCOL_TITLES.get(protocol, protocol)
        for protocol in values
    ) or "-"


def canonical_payment_event_key(
    event_key: str,
    kind: str,
    payload: dict[str, Any] | None,
) -> str:
    if str(kind or "") != "payment_approved" or not isinstance(payload, dict):
        return str(event_key)

    try:
        order_id = int(payload.get("order_id"))
        payment_id = int(payload.get("payment_id"))
        subscription_id = int(payload.get("subscription_id"))
    except (TypeError, ValueError):
        return str(event_key)

    if order_id <= 0 or payment_id <= 0 or subscription_id <= 0:
        return str(event_key)

    return (
        f"payment-approved:order:{order_id}:"
        f"payment:{payment_id}:subscription:{subscription_id}"
    )


def _queue_telegram_notification(
    db,
    *,
    user_id: int,
    event_key: str,
    kind: str,
    payload: dict,
):
    assert _ORIGINAL_QUEUE is not None
    return _ORIGINAL_QUEUE(
        db,
        user_id=user_id,
        event_key=canonical_payment_event_key(event_key, kind, payload),
        kind=kind,
        payload=payload,
    )


def _delivery_is_customer_sendable(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False

    link = str(
        payload.get("subscription_link")
        or payload.get("share_url")
        or ""
    ).strip()
    if not link:
        return False

    account = payload.get("account")
    if isinstance(account, dict) and str(account.get("username") or "").strip():
        return True

    credentials = payload.get("credentials")
    if not isinstance(credentials, list):
        return False

    for row in credentials:
        if not isinstance(row, dict):
            continue
        items = row.get("items")
        if isinstance(items, list) and any(
            isinstance(item, dict) and bool(item)
            for item in items
        ):
            return True
        if isinstance(items, dict) and bool(items):
            return True

    return False


async def _fulfill_paid_order_delivery_safe(order_id: int, db):
    """Preserve a paid order when its subscription is already deliverable.

    The canonical store fulfillment remains authoritative. This wrapper only
    recovers the narrow case where it returns HTTP 502 after creating a usable
    subscription, or where a previous attempt already left a usable
    ``provision_failed`` subscription behind.
    """

    assert _ORIGINAL_FULFILL is not None

    from .routers import store
    from .store_models import StoreOrder

    order = db.get(StoreOrder, int(order_id))
    if (
        order is not None
        and str(order.status or "") in {"paid", "provisioning", "provision_failed"}
        and order.subscription_id
    ):
        snapshot = store._existing_delivery_snapshot(order, db)
        if _delivery_is_customer_sendable(snapshot):
            previous_error = str(order.error_text or "").strip()
            order = store._mark_order_fulfilled(order, db)
            return {
                **store._order_out(order),
                "delivery_ready": True,
                "recovered_existing_delivery": True,
                "partial_provisioning": bool(previous_error),
                "provision_warnings": [previous_error] if previous_error else [],
            }

    try:
        return await _ORIGINAL_FULFILL(int(order_id), db)
    except Exception as exc:
        if int(getattr(exc, "status_code", 0) or 0) != 502:
            raise

        db.rollback()
        order = db.get(StoreOrder, int(order_id))
        if order is None or not order.subscription_id:
            raise

        snapshot = store._existing_delivery_snapshot(order, db)
        if not _delivery_is_customer_sendable(snapshot):
            raise

        previous_error = str(order.error_text or getattr(exc, "detail", "") or "").strip()
        order = store._mark_order_fulfilled(order, db)
        return {
            **store._order_out(order),
            "delivery_ready": True,
            "recovered_existing_delivery": True,
            "partial_provisioning": True,
            "provision_warnings": [previous_error] if previous_error else [],
        }


def install() -> None:
    global _ORIGINAL_QUEUE, _ORIGINAL_FULFILL, _INSTALLED

    if _INSTALLED:
        return

    # Patch the purchase helper before telegram_runtime_bot builds its purchase
    # router. Importing this module has no network or DB side effects.
    from . import telegram_purchase_bot

    telegram_purchase_bot.plan_protocols = canonical_plan_protocols
    telegram_purchase_bot.protocol_text = canonical_protocol_text

    _ORIGINAL_QUEUE = telegram_notify_service.queue_telegram_notification
    telegram_notify_service.queue_telegram_notification = _queue_telegram_notification

    # Install the narrow paid-order recovery wrapper before the durable payment
    # fulfillment service imports the Store helper by value.
    from .routers import store

    _ORIGINAL_FULFILL = store._fulfill_paid_order
    store._fulfill_paid_order = _fulfill_paid_order_delivery_safe

    # If another import-time compatibility module happened to import one of the
    # known producers first, replace only references which still point at the
    # original functions. Future imports receive the wrapped functions.
    for module_name in (
        "app.routers.store",
        "app.routers.payments",
        "app.services.payment_automation",
        "app.services.payment_native_crypto",
        "app.services.payment_native_crypto_exact",
        "app.services.payment_fulfillment_fast_path",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        if getattr(module, "queue_telegram_notification", None) is _ORIGINAL_QUEUE:
            setattr(module, "queue_telegram_notification", _queue_telegram_notification)
        if getattr(module, "_fulfill_paid_order", None) is _ORIGINAL_FULFILL:
            setattr(module, "_fulfill_paid_order", _fulfill_paid_order_delivery_safe)

    # Keep the registry ordering available for smoke/diagnostics without
    # changing the telegram module's historical PROTOCOLS constant.
    telegram_purchase_bot.FULL_PROTOCOL_KEYS = tuple(ALL_PROTOCOL_KEYS)
    _INSTALLED = True
