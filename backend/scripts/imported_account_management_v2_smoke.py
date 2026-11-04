from pathlib import Path
base = Path(__file__).resolve().parents[1] / 'app'
api = (base / 'routers/telegram_subscription_import_v1.py').read_text()
bot = (base / 'telegram_subscription_import_bot_v1.py').read_text()
compile(api, '<api>', 'exec')
compile(bot, '<bot>', 'exec')
for item in ['plan_name', 'traffic_remaining_gb', 'days_remaining', 'management_mode']:
    assert item in api, item
for item in ['subimp:refresh:', 'subimp:link:', 'subimprenew:', 'subimprenewconfirm:', 'subimp:ask:password:', 'subimp:confirm:', 'subimp:remove:']:
    assert item in bot, item
assert '/v1/support/tickets' in bot
assert 'await _read_import(callback, sub_id)' in bot
assert 'from .telegram_support_bot import _user_token' in bot
assert 'sub.user_id =' not in api
print('IMPORTED_ACCOUNT_MANAGEMENT_V2=PASS')
