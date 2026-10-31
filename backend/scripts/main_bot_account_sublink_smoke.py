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

# Main-bot UI contract: account link recovery is driven by My Accounts, not by
# VPN username/password. This is required for migrated V2Ray subscriptions
# imported from external panels which legitimately have no password identity.
assert 'ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"' in feature_source
assert 'ACCOUNT_LINK_CALLBACK_PREFIX = "account_link:"' in feature_source
assert '"/v1/subscriptions/me"' in feature_source
assert feature_source.count('"/v1/subscriptions/me"') >= 2
assert 'f"/v1/customer/subscriptions/{sub_id}/connection-info"' in feature_source
assert "F.data.startswith(ACCOUNT_LINK_CALLBACK_PREFIX)" in feature_source
assert "_status_value(row) == \"active\"" in feature_source
assert 'link.startswith(("http://", "https://"))' in feature_source
assert "برای اشتراک‌های مهاجرتی نیازی به نام کاربری یا رمز VPN نیست" in feature_source

# Regression guard: never reintroduce VPN credential proof as a prerequisite
# for a Telegram-linked customer selecting one of their own My Accounts rows.
assert "AccountLinkState.username" not in feature_source
assert "AccountLinkState.password" not in feature_source
assert '"/v1/telegram/account-link/resolve"' not in feature_source
assert '"password": password' not in feature_source
assert "bot_auth=True" not in feature_source

# Callback IDs are not trusted on their own. The bot re-reads My Accounts and
# the customer connection-info endpoint performs the server-side ownership
# check before returning the canonical subscription link.
callback_handler = feature_source[
    feature_source.index("async def account_link_pick"):
]
assert '"/v1/subscriptions/me"' in callback_handler
assert "_subscription_id(row) == sub_id" in callback_handler
assert "_status_value(row) == \"active\"" in callback_handler
assert 'f"/v1/customer/subscriptions/{sub_id}/connection-info"' in callback_handler
assert "token=token" in callback_handler

# The bot module must not gain direct database access. Ownership remains behind
# authenticated customer APIs. Keep the old bot-secret resolver intact only as
# backward compatibility for older clients/releases; the main bot no longer
# uses it for My Accounts recovery.
assert "db.query(" not in feature_source
assert "db.get(" not in feature_source
assert "from .models import" not in feature_source
assert "dependencies=[Depends(bot_guard)]" in lookup_source
assert "hmac.compare_digest(" in lookup_source
assert "_FAILURE_LIMIT = 6" in lookup_source

# The feature must be attached to a router included before the main router's
# generic fallback, while preserving the existing runtime entrypoint.
assert "original_create_wallet_router" in extension_source
assert "install_account_link_feature(" in extension_source
assert "install_main_bot_extensions()" in guides_source
assert runtime_source.index("from .telegram_guides_bot import") < runtime_source.index("from .telegram_wallet_bot import")
assert runtime_source.index("create_wallet_router(") < runtime_source.index("dp.include_router(router)")

print("MAIN_BOT_ACCOUNT_SUBLINK_SMOKE_OK")
