from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
lookup = (
    ROOT
    / "backend/app/routers/telegram_account_link_lookup.py"
).read_text(encoding="utf-8")
bot = (
    ROOT
    / "backend/app/telegram_account_link_bot.py"
).read_text(encoding="utf-8")
routers_init = (
    ROOT
    / "backend/app/routers/__init__.py"
).read_text(encoding="utf-8")


checks = {
    "bot-secret guard": "dependencies=[Depends(bot_guard)]" in lookup,
    "failed-attempt throttle": "_FAILURE_LIMIT = 6" in lookup and "status_code=429" in lookup,
    "canonical share URL reuse": "from .account_delivery import _share_url" in lookup,
    "migrated endpoint": '"/account-link/resolve-migrated"' in lookup,
    "migration record restriction": "MigrationImportRecord" in lookup and 'MigrationImportRecord.status == "imported"' in lookup,
    "migrated username lookup": "func.lower(Subscription.account_username)" in lookup,
    "active migration guard": "Subscription.status == SubscriptionStatus.ACTIVE" in lookup,
    "expired migration guard": "Subscription.expires_at > now" in lookup,
    "duplicate fail closed": ".limit(2)" in lookup and "if len(matches) != 1" in lookup,
    "main bot migrated API": '"/v1/telegram/account-link/resolve-migrated"' in bot and "bot_auth=True" in bot,
    "main bot username only": '"username": username' in bot and '"password": password' not in bot,
    "my accounts untouched": '"/v1/subscriptions/me"' not in bot,
    "legacy credential endpoint retained": '"/account-link/resolve"' in lookup,
    "legacy constant-time password compare": "hmac.compare_digest(" in lookup,
    "legacy credential error": "نام کاربری یا رمز عبور اکانت اشتباه است" in lookup,
    "route imported": "telegram_account_link_lookup" in routers_init,
    "route mounted": "include_router(_telegram_account_link_lookup_router)" in routers_init,
}

failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit(
        "TELEGRAM_ACCOUNT_LINK_CREDENTIALS_SMOKE_FAILED: "
        + ", ".join(failed)
    )

print("TELEGRAM_ACCOUNT_LINK_CREDENTIALS_SMOKE_OK")
