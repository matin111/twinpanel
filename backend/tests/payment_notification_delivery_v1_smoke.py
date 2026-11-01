from __future__ import annotations

from pathlib import Path


store_path = Path("app/routers/store.py")
store_source = store_path.read_text(encoding="utf-8")
compile(store_source, str(store_path), "exec")

sms_path = Path("app/routers/sms_reader.py")
sms_source = sms_path.read_text(encoding="utf-8")
compile(sms_source, str(sms_path), "exec")

assert "from ..payment_models import PaymentIntent" in store_source
assert "from ..telegram_notify_service import queue_telegram_notification" in store_source
assert "def _queue_fulfilled_order_notification(" in store_source
assert 'kind="payment_approved"' in store_source
assert 'event_prefix = "payment-auto-approved" if auto_verified else "payment-approved"' in store_source
assert "_queue_fulfilled_order_notification(order, db)" in store_source

# Both the direct admin-confirm path and SMS auto-verification must terminate at
# the same canonical store fulfillment boundary, where the notification is now
# durably queued for the existing main-bot worker.
confirm_section = store_source.split("async def confirm_store_order(", 1)[1]
assert "return await _fulfill_paid_order(order_id, db)" in confirm_section
assert "result = await _fulfill_paid_order(" in sms_source

print("PAYMENT_NOTIFICATION_DELIVERY_V1_OK")
