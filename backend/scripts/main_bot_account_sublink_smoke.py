from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURE = ROOT / "app" / "telegram_account_link_bot.py"
LOOKUP = ROOT / "app" / "routers" / "telegram_account_link_lookup.py"
EXTENSIONS = ROOT / "app" / "telegram_main_extensions.py"
GUIDES = ROOT / "app" / "telegram_guides_bot.py"
RUNTIME = ROOT / "app" / "telegram_runtime_bot.py"

feature_source = FEATURE.read_text(encoding="utf-8")
lookup_source = LOOKUP.read_text(encoding="utf-8")
extension_source = EXTENSIONS.read_text(encoding="utf-8")
guides_source = GUIDES.read_text(encoding="utf-8")
runtime_source = RUNTIME.read_text(encoding="utf-8")

for source in (
    feature_source,
    lookup_source,
    extension_source,
    guides_source,
):
    ast.parse(source)

# Main-bot contract: account-link recovery is source/protocol agnostic. It asks
# only for the account username and resolves the canonical TwinPanel share URL
# for a subscription owned by the user linked to this Telegram ID.
assert 'ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"' in feature_source
assert 'ACCOUNT_LINK_CALLBACK = "account_link:start"' in feature_source
assert 'CANCEL_CALLBACK = "account_link:cancel"' in feature_source
assert 'MAIN_HOME_CALLBACK = "main:home"' in feature_source
assert "AccountLinkState.username" in feature_source
assert "نام کاربری VPN اکانت خود را وارد کنید" in feature_source
assert "اکانت مهاجرتی" not in feature_source
assert "V2Ray" not in feature_source
assert '"/v1/telegram/account-link/resolve-owned"' in feature_source
assert '"telegram_id": message.from_user.id' in feature_source
assert '"username": username' in feature_source
assert "bot_auth=True" in feature_source
assert 'link.startswith(("http://", "https://"))' in feature_source

# Entire primary navigation is inline. No newly rendered main/connect/account-link
# control may depend on Telegram's persistent ReplyKeyboard.
assert "def _main_menu_keyboard():" in feature_source
assert "return InlineKeyboardMarkup(" in feature_source
assert "\n    KeyboardButton,\n" not in feature_source
assert "ReplyKeyboardMarkup" not in feature_source
for callback_id in (
    "account_link:start",
    "main:dashboard",
    "subs:list",
    "shop:list",
    "wallet:refresh",
    "mlearn:g:root",
    "mlearn:d:root",
    "ts:send",
    "main:account",
    "main:connect-account",
):
    assert callback_id in feature_source

# A cached ReplyKeyboard from rc.419 and older must be explicitly removed on
# /start before the existing start handler renders the new inline menu.
assert "from aiogram.filters import CommandStart" in feature_source
assert "ReplyKeyboardRemove" in feature_source
assert "@router.message(CommandStart())" in feature_source
assert "async def inline_main_start" in feature_source
assert "reply_markup=ReplyKeyboardRemove()" in feature_source
assert "await main_runtime.start(" in feature_source
assert feature_source.index("@router.message(CommandStart())") < feature_source.index(
    "@router.callback_query(F.data == MAIN_HOME_CALLBACK)"
)

# Account-link must be the first, full-width row. Remaining main actions are
# compact two-column inline rows.
menu_start = feature_source.index("def _main_menu_keyboard():")
menu_end = feature_source.index("def _connect_keyboard():")
menu_source = feature_source[menu_start:menu_end]
assert menu_source.index("text=ACCOUNT_LINK_BUTTON") < menu_source.index('text="🏠 داشبورد"')
assert menu_source.count("InlineKeyboardButton(") == 9
assert 'text="🏠 داشبورد"' in menu_source
assert 'text="📦 اشتراک‌های من"' in menu_source
assert 'text="🛒 خرید اشتراک"' in menu_source
assert 'text="💰 کیف پول"' in menu_source
assert 'text="📚 آموزش"' in menu_source
assert 'text="⬇️ دانلود برنامه"' in menu_source
assert 'text="🎫 پشتیبانی"' in menu_source
assert 'text="👤 حساب من"' in menu_source

# Runtime patch replaces both persistent primary keyboards at startup while old
# text handlers remain available only for stale keyboards from previous builds.
assert "main_runtime.main_keyboard = _main_menu_keyboard" in feature_source
assert "main_runtime.connect_keyboard = _connect_keyboard" in feature_source
assert "@router.callback_query(F.data == MAIN_HOME_CALLBACK)" in feature_source
assert "@router.callback_query(F.data == \"main:dashboard\")" in feature_source
assert "@router.callback_query(F.data == \"main:account\")" in feature_source
assert "@router.callback_query(F.data == \"main:connect-account\")" in feature_source
assert "main_runtime._customer_dashboard_data(" in feature_source
assert "main_runtime._dashboard_text(data)" in feature_source
assert "main_runtime.status(" in feature_source
assert "main_runtime.LinkState.email" in feature_source

# Active account-link flow uses inline start/cancel callbacks. Legacy message
# handlers are retained so a stale rc.418/rc.419 ReplyKeyboard cannot trap users.
assert "@router.callback_query(F.data == ACCOUNT_LINK_CALLBACK)" in feature_source
assert "async def account_link_start_inline" in feature_source
assert "@router.callback_query(F.data == CANCEL_CALLBACK)" in feature_source
assert "async def account_link_cancel_inline" in feature_source
assert 'text="❌ لغو عملیات"' in feature_source
assert "await callback.answer()" in feature_source
assert "@router.message(F.text == CANCEL_BUTTON)" in feature_source
assert "@router.message(F.text == ACCOUNT_LINK_BUTTON)" in feature_source
assert "MemoryStorage()" in runtime_source

# Regression guards: recovery must not become a My Accounts picker or a
# username+password FSM again.
assert '"/v1/subscriptions/me"' not in feature_source
assert "/v1/customer/subscriptions/" not in feature_source
assert "password = State()" not in feature_source
assert '"password": password' not in feature_source
assert '"/v1/telegram/account-link/resolve"' not in feature_source

# Resolver contract: source/protocol agnostic, but ownership scoped. The bot may
# only retrieve a username inside subscriptions owned by the TwinPanel user
# linked to the calling Telegram ID.
assert '"/account-link/resolve-owned"' in lookup_source
assert "TelegramOwnedAccountLinkLookupIn" in lookup_source
assert "TelegramUserLink" in lookup_source
assert "db.get(TelegramUserLink, telegram_id)" in lookup_source
assert "Subscription.user_id == int(telegram_link.user_id)" in lookup_source
assert "func.lower(Subscription.account_username)" in lookup_source
assert "Subscription.status == SubscriptionStatus.ACTIVE" in lookup_source
assert "Subscription.expires_at > now" in lookup_source
assert ".limit(2)" in lookup_source
assert "if len(matches) != 1" in lookup_source
assert "MigrationImportRecord" not in lookup_source
assert "migration_source" not in lookup_source
assert "_FAILURE_LIMIT = 6" in lookup_source
assert "status_code=429" in lookup_source
assert "dependencies=[Depends(bot_guard)]" in lookup_source
assert "from .account_delivery import _share_url" in lookup_source

# rc.416 compatibility alias remains, but it must delegate to the same owned
# resolver rather than reintroducing migration-only behavior.
assert '"/account-link/resolve-migrated"' in lookup_source
assert "resolve_migrated_account_link_compat" in lookup_source
assert "return _resolve_owned_subscription(payload, db)" in lookup_source

# The old credential resolver remains available for backward compatibility,
# but the main bot no longer uses it.
assert '"/account-link/resolve"' in lookup_source
assert "hmac.compare_digest(" in lookup_source
assert "TelegramAccountLinkLookupIn" in lookup_source

# The feature must not gain direct database/model imports or mutate provisioning.
feature_tree = ast.parse(feature_source)
feature_imports = []
for node in ast.walk(feature_tree):
    if isinstance(node, ast.Import):
        feature_imports.extend(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        feature_imports.append(module)
        feature_imports.extend(f"{module}.{alias.name}" for alias in node.names)

assert not any("models" in item for item in feature_imports)
assert "db.query(" not in feature_source
assert "db.get(" not in feature_source
assert "provision(" not in feature_source

# The extension is attached before the main router's generic fallback while
# preserving the existing runtime entrypoint.
assert "original_create_wallet_router" in extension_source
assert "install_account_link_feature(" in extension_source
assert "install_main_bot_extensions()" in guides_source
assert runtime_source.index("from .telegram_guides_bot import") < runtime_source.index("from .telegram_wallet_bot import")
assert runtime_source.index("create_wallet_router(") < runtime_source.index("dp.include_router(router)")
assert 'await message.answer(\n        "این بخش در حال اتصال به "' in runtime_source

print("MAIN_BOT_ACCOUNT_SUBLINK_SMOKE_OK")
