from __future__ import annotations

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session as OrmSession

from .customer_wallet_models import CustomerWalletTopup
from .database import SessionLocal
from .models import User
from .reseller_bot_order_models import ResellerBotOrder
from .reseller_notification_models import ResellerNotification


_SESSION_EVENTS_KEY = "twinpanel_reseller_receipt_panel_events"
_RESELLER_TOPUP_PREFIX = "reseller_card:"


def _reseller_id_from_topup(row: CustomerWalletTopup) -> int | None:
    method = str(row.method or "").strip().lower()
    if not method.startswith(_RESELLER_TOPUP_PREFIX):
        return None

    parts = method.split(":")
    if len(parts) < 2 or not parts[1].isdigit():
        return None

    reseller_id = int(parts[1])
    return reseller_id if reseller_id > 0 else None


def _status_changed_to_review(row) -> bool:
    if str(getattr(row, "status", "") or "") != "awaiting_review":
        return False

    try:
        return inspect(row).attrs.status.history.has_changes()
    except Exception:
        return False


def _collect_event(session: OrmSession, payload: dict) -> None:
    events = session.info.setdefault(_SESSION_EVENTS_KEY, {})
    events[str(payload["event_key"])] = payload


@event.listens_for(OrmSession, "after_flush")
def _collect_reseller_receipt_events(session, flush_context) -> None:
    del flush_context

    for row in list(session.new) + list(session.dirty):
        if not _status_changed_to_review(row):
            continue

        if isinstance(row, CustomerWalletTopup):
            reseller_id = _reseller_id_from_topup(row)
            if not reseller_id or not row.id:
                continue

            _collect_event(
                session,
                {
                    "event_key": (
                        f"reseller-wallet-topup:{reseller_id}:"
                        f"{int(row.id)}:submitted"
                    ),
                    "reseller_id": int(reseller_id),
                    "user_id": int(row.user_id),
                    "title": "رسید شارژ کیف پول جدید",
                    "amount_toman": int(row.amount_toman or 0),
                    "kind": "warning",
                    "source": "bot_wallet",
                    "route": "bot-wallet",
                    "reference": int(row.id),
                    "type": "wallet",
                },
            )
            continue

        if isinstance(row, ResellerBotOrder):
            if not row.id or not row.reseller_id:
                continue

            is_renewal = str(row.payment_note or "").startswith("renewal:")
            _collect_event(
                session,
                {
                    "event_key": (
                        f"reseller-bot-order:{int(row.reseller_id)}:"
                        f"{int(row.id)}:submitted"
                    ),
                    "reseller_id": int(row.reseller_id),
                    "user_id": int(row.customer_user_id),
                    "title": (
                        "رسید تمدید ربات جدید"
                        if is_renewal
                        else "رسید خرید ربات جدید"
                    ),
                    "amount_toman": int(row.sell_price_toman or 0),
                    "kind": "warning",
                    "source": "bot_order",
                    "route": "orders",
                    "reference": int(row.id),
                    "type": "renewal" if is_renewal else "purchase",
                },
            )


@event.listens_for(OrmSession, "after_commit")
def _persist_reseller_receipt_events(session) -> None:
    pending = session.info.pop(_SESSION_EVENTS_KEY, {})
    if not pending:
        return

    db = SessionLocal()
    try:
        for payload in pending.values():
            event_key = str(payload["event_key"])
            exists = (
                db.query(ResellerNotification.id)
                .filter(ResellerNotification.event_key == event_key)
                .first()
            )
            if exists:
                continue

            user = db.get(User, int(payload["user_id"]))
            customer_name = (
                str(getattr(user, "full_name", "") or "").strip()
                or f"کاربر #{int(payload['user_id'])}"
            )
            amount = int(payload["amount_toman"] or 0)
            reference = int(payload["reference"])

            if payload["type"] == "wallet":
                message = (
                    f"رسید درخواست شارژ کیف پول #{reference} از "
                    f"{customer_name} به مبلغ {amount:,} تومان برای بررسی ثبت شد."
                )
            elif payload["type"] == "renewal":
                message = (
                    f"رسید تمدید سفارش #{reference} از {customer_name} "
                    f"به مبلغ {amount:,} تومان برای بررسی ثبت شد."
                )
            else:
                message = (
                    f"رسید خرید سفارش #{reference} از {customer_name} "
                    f"به مبلغ {amount:,} تومان برای بررسی ثبت شد."
                )

            db.add(
                ResellerNotification(
                    reseller_id=int(payload["reseller_id"]),
                    event_key=event_key,
                    title=str(payload["title"]),
                    message=message,
                    kind=str(payload["kind"]),
                    source=str(payload["source"]),
                    route=str(payload["route"]),
                )
            )

        db.commit()
    except Exception:
        db.rollback()
        # Receipt submission is the business-critical operation. Notification
        # persistence must never make a committed payment proof fail.
    finally:
        db.close()


@event.listens_for(OrmSession, "after_rollback")
def _clear_reseller_receipt_events(session) -> None:
    session.info.pop(_SESSION_EVENTS_KEY, None)
