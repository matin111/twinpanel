"""Check direct Telegram receipt push without sending real messages."""
import ast
from pathlib import Path
root=Path(__file__).resolve().parents[1]/"app"
source=(root/"services/telegram_admin_receipt_push.py").read_text()
loop=(root/"services/customer_maintenance.py").read_text()
bot=(root/"telegram_admin_ops_v1.py").read_text()
api=(root/"routers/telegram_admin_ops_v1.py").read_text()
ast.parse(source)
ast.parse(loop)
for required in (
    'PaymentIntent.status.in_', 'CustomerWalletTopup.status.in_',
    '_manual_purchase(x)', '_manual_topup(x)',
    '_is_reseller_bot_internal_user(db, x.user_id)', '_is_reseller_scoped_topup(x)',
    'telegram.admin.grant.', 'user.role == UserRole.ADMIN',
    'on_conflict_do_nothing', 'with_for_update(skip_locked=True)',
    'STALE_SECONDS = 300', 'setting_value = "sent"',
    'if not receipt:', '_reserve(db, kind, item_id, chat_id)',
    'await _deliver(', 'base + "sendPhoto"', 'base + method',
    '"✅ تأیید رسید"', '"❌ رد رسید"',
    'adm:do:approve:{kind}:{item_id}', 'adm:ask:reject:{kind}:{item_id}',
):
    assert required in source, required
assert 'push_manual_receipts_once()' in loop
assert 'last_manual_receipt_push' in loop
assert 'F.data.startswith("adm:ask:")' in bot
assert 'F.data.startswith("adm:do:")' in bot
assert 'async def receipt_detail(' in bot
assert 'callback.message.edit_caption(' in bot
assert 'callback.message.edit_text(' in bot
assert 'if not _manual_purchase(row):' in api
assert '_admin(db, payload.telegram_id)' in api
print("DIRECT_ADMIN_MANUAL_RECEIPT_BUTTONS=PASS")
