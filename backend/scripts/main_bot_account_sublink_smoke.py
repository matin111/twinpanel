from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURE = ROOT / "app" / "telegram_account_link_bot.py"
EXTENSIONS = ROOT / "app" / "telegram_main_extensions.py"
GUIDES = ROOT / "app" / "telegram_guides_bot.py"
RUNTIME = ROOT / "app" / "telegram_runtime_bot.py"

feature_source = FEATURE.read_text(encoding="utf-8")
extension_source = EXTENSIONS.read_text(encoding="utf-8")
guides_source = GUIDES.read_text(encoding="utf-8")
runtime_source = RUNTIME.read_text(encoding="utf-8")

for source in (
    feature_source,
    extension_source,
    guides_source,
):
    ast.parse(source)

assert 'ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"' in feature_source
assert "AccountLinkState.username" in feature_source
assert '"/v1/subscriptions/me"' in feature_source
assert 'f"{sub_id}/manage"' in feature_source
assert 'f"{sub_id}/connection-info"' in feature_source
assert "account_username.casefold() == wanted" in feature_source
assert 'link.startswith(("http://", "https://"))' in feature_source
assert 'CANCEL_BUTTON = "❌ لغو"' in feature_source

# The lookup must stay inside token-scoped customer endpoints.
assert "db.query(" not in feature_source
assert "db.get(" not in feature_source
assert "from .models import" not in feature_source
assert "Subscription.account_username" not in feature_source

# The feature must be attached to a router included before the main router's
# generic fallback, while preserving the existing runtime entrypoint.
assert "original_create_wallet_router" in extension_source
assert "install_account_link_feature(" in extension_source
assert "install_main_bot_extensions()" in guides_source
assert runtime_source.index("from .telegram_guides_bot import") < runtime_source.index("from .telegram_wallet_bot import")
assert runtime_source.index("create_wallet_router(") < runtime_source.index("dp.include_router(router)")

print("MAIN_BOT_ACCOUNT_SUBLINK_SMOKE_OK")
