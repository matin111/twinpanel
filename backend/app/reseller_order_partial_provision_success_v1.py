from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Iterable


logger = logging.getLogger(__name__)
_INSTALLED = False


def _protocol_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    if name == "xray":
        return "v2ray"
    return name


def _requested_protocols(db, subscription_id: int) -> set[str]:
    from .models import SubscriptionProtocol

    return {
        _protocol_name(row[0])
        for row in (
            db.query(SubscriptionProtocol.protocol)
            .filter(SubscriptionProtocol.subscription_id == int(subscription_id))
            .all()
        )
        if _protocol_name(row[0])
    }


def _pair_protocols(rows: Iterable[Any]) -> set[str]:
    result: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = _protocol_name(row.get("protocol"))
        if name:
            result.add(name)
    return result


def _credential_protocols(rows: Iterable[Any]) -> set[str]:
    """Return protocols with at least one usable item in modern delivery output."""
    result: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue

        name = _protocol_name(row.get("protocol"))
        if not name:
            continue

        items = row.get("items")
        if isinstance(items, list):
            usable = any(isinstance(item, dict) and bool(item) for item in items)
        else:
            usable = isinstance(items, dict) and bool(items)

        if usable:
            result.add(name)

    return result


def reconcile_reseller_provision_result(
    provision: Any,
    requested_protocols: set[str],
) -> Any:
    """Treat per-node errors as warnings only when the order is deliverable.

    Both the legacy account driver and the modern 15-protocol driver may report
    node-specific failures after already creating a usable credential on another
    selected node. Reseller order review must not convert that useful partial
    success into a total order failure. Every requested protocol still needs at
    least one usable delivery item.
    """
    if not isinstance(provision, dict):
        return provision

    errors = list(
        provision.get("errors")
        or provision.get("provision_errors")
        or []
    )
    if not errors:
        return provision

    requested = {
        _protocol_name(value)
        for value in requested_protocols
        if _protocol_name(value)
    }
    if not requested:
        return provision

    good_protocols = _pair_protocols(
        list(provision.get("created_pairs") or [])
        + list(provision.get("reused_pairs") or [])
    )
    good_protocols.update(
        _credential_protocols(provision.get("credentials") or [])
    )

    missing = sorted(requested - good_protocols)
    if missing:
        return provision

    patched = dict(provision)
    patched["ok"] = True
    patched["provision_warnings"] = errors
    # reseller_bot_orders historically treats any item in either error
    # collection as a total failure. Clear only the reseller-local copy; the
    # canonical provision_account result is otherwise untouched.
    patched["errors"] = []
    patched["provision_errors"] = []
    return patched


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # Patch only the reseller commerce module's imported alias. The canonical
    # account_delivery.provision_account function used by admin/customer flows
    # remains unchanged.
    from .routers import reseller_bot_orders as reseller_orders

    original = reseller_orders.provision_account
    if getattr(original, "_twinpanel_reseller_partial_success_v1", False):
        _INSTALLED = True
        return

    @wraps(original)
    async def wrapped_provision_account(subscription_id: int, db, *args, **kwargs):
        result = await original(subscription_id, db, *args, **kwargs)
        requested = _requested_protocols(db, int(subscription_id))
        reconciled = reconcile_reseller_provision_result(result, requested)

        if (
            isinstance(reconciled, dict)
            and reconciled is not result
            and reconciled.get("provision_warnings")
        ):
            logger.warning(
                "reseller order provisioning completed with node warnings: "
                "subscription_id=%s protocols=%s warnings=%s",
                int(subscription_id),
                sorted(requested),
                reconciled.get("provision_warnings"),
            )
        return reconciled

    wrapped_provision_account._twinpanel_reseller_partial_success_v1 = True
    reseller_orders.provision_account = wrapped_provision_account
    _INSTALLED = True
