"""Protect imported-account password changes; no network, database or user secrets."""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "app"
api = (root / "routers/telegram_subscription_import_v1.py").read_text()
bot = (root / "telegram_subscription_import_bot_v1.py").read_text()
for p in [root / "routers/telegram_subscription_import_v1.py", root / "telegram_subscription_import_bot_v1.py"]:
    compile(p.read_text(), str(p), "exec")

assert '@router.post("/{telegram_id}/{subscription_id}/change-password"' in api
assert 'dependencies=[Depends(bot_guard)]' in api
assert 'imported_accounts.c.telegram_id == telegram_id' in api
assert 'imported_accounts.c.subscription_id == subscription_id' in api
assert 'hmac.compare_digest' in api
assert '_guard_attempts(telegram_id)' in api
assert '_record_failure(telegram_id)' in api
assert 'sub.account_password_encrypted = payload.new_password' in api
assert 'refresh_simple_passwords(subscription_id=sub.id, db=db)' in api
assert 'SubscriptionProtocol.protocol.in_(["cisco", "l2tp"])' in api
assert 'db.rollback()' in api

assert 'callback_data=f"subimp:password:{sub_id}"' in bot
assert 'class PasswordChangeState(StatesGroup)' in bot
assert 'PasswordChangeState.current' in bot
assert 'PasswordChangeState.new' in bot
assert 'await message.delete()' in bot
assert 'message.chat.type != "private"' in bot
assert '/change-password' in bot
assert '"current_password": old' in bot and '"new_password": value' in bot
assert 'await state.clear()' in bot
print("IMPORTED_ACCOUNT_PASSWORD_CHANGE=PASS")
