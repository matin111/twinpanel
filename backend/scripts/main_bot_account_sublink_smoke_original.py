"""Main Telegram bot account-link and subscription navigation regression.

Current main bot delegates legacy account-link handlers to
telegram_account_link_bot_original.py; assertions must inspect the actual
delegated implementation, rather than an obsolete single-file layout.
"""
from pathlib import Path
import ast
from aiogram.types import InlineKeyboardButton

root = Path(__file__).resolve().parents[1]
app = root / "app"
base = (app / "telegram_account_link_bot_original.py").read_text("utf-8")
wrapper = (app / "telegram_account_link_bot.py").read_text("utf-8")
lookup = (app / "routers/telegram_account_link_lookup.py").read_text("utf-8")
runtime = (app / "telegram_runtime_bot.py").read_text("utf-8")
extensions = (app / "telegram_main_extensions.py").read_text("utf-8")
guides = (app / "telegram_guides_bot.py").read_text("utf-8")
import_bot = (app / "telegram_subscription_import_bot_v1.py").read_text("utf-8")
import_api = (app / "routers/telegram_subscription_import_v1.py").read_text("utf-8")

for name, source in {
    "base": base,
    "wrapper": wrapper,
    "lookup": lookup,
    "runtime": runtime,
    "extensions": extensions,
    "guides": guides,
    "import_bot": import_bot,
    "import_api": import_api,
}.items():
    ast.parse(source, filename=name)

# aiogram keeps inline button styling in Bot API serialized payload.
button = InlineKeyboardButton(text="probe", callback_data="probe", style="primary")
assert button.model_dump(exclude_none=True).get("style") == "primary"

# Established account link by VPN username must remain reachable and not
# accidentally become subscription-import or a username/password prompt.
assert 'ACCOUNT_LINK_CALLBACK = "account_link:start"' in base
assert "AccountLinkState.username" in base
assert '"/v1/telegram/account-link/resolve-username"' in base
assert '"telegram_id": message.from_user.id' in base
assert '"username": username' in base
assert "bot_auth=True" in base
assert "AccountLinkState.password" not in base
assert '"/account-link/resolve-username"' in lookup
assert "status_code=429" in lookup

# The current styled navigation wrapper uses the real live main menu.
assert "_base.install_account_link_feature(" in wrapper
assert "main_runtime.main_keyboard = _main_menu_keyboard" in wrapper
assert "live_button_styles()" in wrapper
assert "callback_data=\"subs:list\"" in wrapper
assert "callback_data=_base.ACCOUNT_LINK_CALLBACK" in wrapper
assert "MAIN_HOME_CALLBACK" in wrapper
assert "reseller_request_conditions" in wrapper
assert "install_subscription_ui(main_runtime)" in wrapper

# Existing bot registration and inline menus stay intact.
assert "install_account_link_feature(" in extensions
assert "install_main_bot_extensions()" in guides
assert "MemoryStorage()" in runtime
assert '@router.callback_query(\n    F.data == "subs:list"' in runtime
assert "def subscription_list_keyboard(rows, imported=None):" in runtime
assert "subimp:add" in runtime and "subimp:" in runtime

# New addition is scoped to the bot user's share-token capability. It MUST
# NEVER transfer the subscription's original user ownership.
assert "install_subscription_import(router, request_fn)" in wrapper
assert "ImportLinkState.link" in import_bot
assert "subimp:remove:" in import_bot
assert '"/v1/telegram/account-import/add"' in import_bot
assert "bot_auth=True" in import_bot
assert "_subscription_from_share_token(token, db)" in import_api
assert "Subscription.user_id =" not in import_api
assert "sub.user_id =" not in import_api
assert "dependencies=[Depends(bot_guard)]" in import_api

print("MAIN_BOT_ACCOUNT_SUBLINK_SMOKE_OK")
