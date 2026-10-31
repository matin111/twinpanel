from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURE = ROOT / "app" / "reseller_bot_subscription_link_runtime.py"
RUNTIME = ROOT / "app" / "reseller_bot_runtime_owned.py"


feature_source = FEATURE.read_text(encoding="utf-8")
runtime_source = RUNTIME.read_text(encoding="utf-8")

ast.parse(feature_source)
ast.parse(runtime_source)

assert 'ACCOUNT_LINK_BUTTON = "🔗 دریافت لینک اکانت"' in feature_source
assert "ResellerSubscriptionLinkState.username" in feature_source
assert "linked_user(" in feature_source
assert "_subscriptions(db, reseller_id, user_id)" in feature_source
assert "account_username" in feature_source
assert "_share_url(db, sub)" in feature_source
assert 'subscription_link.startswith(("http://", "https://"))' in feature_source
assert "reply_markup=_link_keyboard(subscription_link)" in feature_source

# Ownership must stay delegated to the existing reseller-scoped helper.
# Do not allow this feature to introduce direct/global subscription queries.
assert "db.query(Subscription)" not in feature_source
assert "db.query(ResellerSubscription)" not in feature_source
assert "from .models_reseller import ResellerSubscription" not in feature_source
assert "rsublink:cancel" in feature_source

assert "build_subscription_link_router" in runtime_source
assert "subscription_link_main_keyboard" in runtime_source
assert "parent.include_router(\n        build_subscription_link_router(reseller_id)" in runtime_source
assert "legacy_runtime._main_keyboard = subscription_link_main_keyboard" in runtime_source

print("RESELLER_BOT_ACCOUNT_SUBLINK_SMOKE_OK")
