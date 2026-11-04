"""Regression for paid imported-account renewal and browser connection instructions."""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "app"
api = (root / "routers/telegram_subscription_import_v1.py").read_text()
bot = (root / "telegram_subscription_import_bot_v1.py").read_text()
qr = (root / "telegram_subscription_qr_v1.py").read_text()
renewal = (root / "renewal_service.py").read_text()
models = (root / "renewal_models.py").read_text()

for name, source in [("api", api), ("bot", bot), ("qr", qr), ("renewal", renewal), ("models", models)]:
    compile(source, f"<{name}>", "exec")

assert "telegram_imported_renewal_authorizations" in models
assert 'from ..renewal_models import SubscriptionRenewalOrder, imported_renewal_authorizations' in api
assert 'dependencies=[Depends(bot_guard)]' in api
assert 'telegram_id == telegram_id' in api
assert 'imported_accounts.c.subscription_id == subscription_id' in api
assert 'def create_imported_renewal_order(' in api
assert 'renew_subscription_id' in api
assert 'db.add(SubscriptionRenewalOrder(' in api
assert 'imported_renewal_authorizations.insert()' in api
assert 'idempotency_key == key' in api
assert 'int(sub.user_id) == int(payer.user_id)' in api
assert "sub.user_id =" not in api and "sub.status =" not in api

assert "TWINPANEL_IMPORTED_PAID_RENEWAL_V1" in renewal
assert 'imported_renewal_authorizations.c.order_id == order.id' in renewal
assert 'imported_renewal_authorizations.c.subscription_id == sub.id' in renewal
assert 'imported_renewal_authorizations.c.payer_user_id == order.user_id' in renewal

assert 'text="💳 تمدید اکانت"' in bot
assert 'callback_data=f"subimp:renew:{sub_id}"' in bot
assert 'callback_data=f"subimp:renewpay:{sub_id}"' in bot
assert 'renewal_payment_methods_keyboard' in bot
assert '"/v1/payments/methods"' in bot
assert 'bot_auth=True' in bot
assert '"💳 درخواست تمدید"' not in bot
assert '"subimp:ask:renew:' not in bot

assert "داخل مرورگر باز کنید" in qr
assert "صفحه اطلاعات اتصال" in qr
assert "سرورها و پروتکل‌های قابل استفاده" in qr
assert "کد QR برای افزودن" in qr
print("TELEGRAM_IMPORTED_DIRECT_RENEWAL_AND_BROWSER_HELP=PASS")
