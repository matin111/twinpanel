"""Contract smoke for payer-funded renewal of a Telegram-imported subscription.

No database writes or real payment requests are made.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "app"
api = (root / "routers/telegram_subscription_import_v1.py").read_text("utf-8")
bot = (root / "telegram_subscription_import_bot_v1.py").read_text("utf-8")
fulfill = (root / "renewal_service.py").read_text("utf-8")
owned = (root / "routers/customer_subscription_management.py").read_text("utf-8")

for path in (
    root / "routers/telegram_subscription_import_v1.py",
    root / "telegram_subscription_import_bot_v1.py",
    root / "renewal_service.py",
):
    compile(path.read_text("utf-8"), str(path), "exec")

assert '@router.post("/{telegram_id}/{subscription_id}/renew-order"' in api
assert 'dependencies=[Depends(bot_guard)]' in api
assert 'imported_accounts.c.telegram_id == telegram_id' in api
assert 'imported_accounts.c.subscription_id == subscription_id' in api
assert 'StoreOrder.user_id == payer.user_id' in api
assert 'user_id=payer.user_id' in api
assert 'user_id=sub.user_id' in api
assert 'SubscriptionRenewalOrder.subscription_id == subscription_id' in api
assert 'if linked is None:' in api

assert 'callback_data=f"subimprenew:{sub_id}"' in bot
assert 'callback_data=f"subimprenewconfirm:{sub_id}:{int(plan[\'id\'])}"' in bot
assert 'subimprenewplan:' in bot
assert '"plan_id": plan_id' in bot
assert 'payload.plan_id' in api
assert 'is_internal_reseller_plan(plan)' in api
assert 'legacy_unmetered' in fulfill
assert 'baseline_limit = max(old_limit, old_used)' in fulfill
assert '"/v1/payments/methods"' in bot
assert 'callback_data=f"renewpay:{int(order[\'id\'])}:{method[\'id\']}"' in bot
assert 'await callback.answer()' in bot
assert 'subimp:ask:renew:' not in bot

# Existing owned-account renewal should still require the owner at creation.
assert 'sub = _owned_subscription(' in owned
# Fulfillment binds the beneficiary to its owner, and remains idempotent.
assert 'int(renewal.user_id)' in fulfill
assert 'int(sub.user_id)' in fulfill
assert 'if renewal.fulfilled_at:' in fulfill
assert 'order.subscription_id = sub.id' in fulfill
assert 'queue_subscription_enforcement(' in fulfill
print("IMPORTED_PAID_RENEWAL_CONTRACT=PASS")
