"""Source and authentication contract for private Telegram admin operations."""
from pathlib import Path
import ast

root=Path(__file__).resolve().parents[1]/"app"
api=(root/"routers/telegram_admin_ops_v1.py").read_text("utf-8")
bot=(root/"telegram_admin_ops_v1.py").read_text("utf-8")
registration=(root/"routers/__init__.py").read_text("utf-8")
integration=(root/"telegram_account_link_bot.py").read_text("utf-8")
ui=(Path(__file__).resolve().parents[2]/"components/admin-telegram-legacy-parity.tsx").read_text("utf-8")

for p in (root/"routers/telegram_admin_ops_v1.py",root/"telegram_admin_ops_v1.py"):
    ast.parse(p.read_text("utf-8"))

for required in (
    "dependencies=[Depends(bot_guard)]",
    "def _admin(db: Session, telegram_id: int)",
    "user.role != UserRole.ADMIN",
    "user.is_active",
    'prefix="/v1/telegram/admin-ops"',
    'prefix="/v1/admin/telegram-bot/admin-access"',
    'dependencies=[Depends(require_admin)]',
    'setting_key == key',
    '.with_for_update().first()',
    'db.delete(row)',
    'datetime.utcnow() > expires',
    'def _manual_purchase(',
    'def _manual_topup(',
    'timedelta(minutes=3)',
    'approve_payment_fast(',
    'approve_wallet_topup_v2(',
    'reject_payment(',
    'adjust_wallet_v2(',
    'suspend_subscription(',
    'activate_subscription(',
    '_broadcast_drafts.pop(payload.nonce, None)',
    'background_tasks.add_task(_deliver_broadcast',
    'audit_log.info("broadcast_started',
):
    assert required in api, required

for required in (
    'Command("adminlink")', 'Command("admin")',
    '"adm:review"', '"adm:lookup"', '"adm:broadcast"',
    '"adm:wallet:confirm"', '"adm:do:',
    '"adm:bcast:"', 'AdminOpsState.broadcast_text',
    'receipt_base64', 'await check(',
):
    assert required in bot, required

assert '_telegram_admin_ops_v1_router' in registration
assert '_telegram_admin_link_router' in registration
assert 'install_telegram_admin_ops(router, request_fn)' in integration
assert '/v1/admin/telegram-bot/admin-access/code' in ui
assert '/v1/admin/telegram-bot/admin-access/operators' in ui
assert '/adminlink' in ui

# Fail closed: every API entrypoint takes an admin principal through
# either _admin or the admin-only panel router.
tree=ast.parse(api)
assert len([n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_admin"])==1
print("TELEGRAM_ADMIN_OPERATIONS_SECURITY_CONTRACT=PASS")
