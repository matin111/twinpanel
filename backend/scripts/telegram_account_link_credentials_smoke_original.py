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
    "owned endpoint": '"/account-link/resolve-owned"' in lookup,
    "telegram owner mapping": "TelegramUserLink" in lookup and "db.get(TelegramUserLink, telegram_id)" in lookup,
    "subscription ownership restriction": "Subscription.user_id == int(telegram_link.user_id)" in lookup,
    "username lookup": "func.lower(Subscription.account_username)" in lookup,
    "active subscription guard": "Subscription.status == SubscriptionStatus.ACTIVE" in lookup,
    "expired subscription guard": "Subscription.expires_at > now" in lookup,
    "duplicate fail closed": ".limit(2)" in lookup and "if len(matches) != 1" in lookup,
    "migration restriction removed": "MigrationImportRecord" not in lookup,
    "main bot owned API": '"/v1/telegram/account-link/resolve-owned"' in bot and "bot_auth=True" in bot,
    "main bot username only": '"username": username' in bot and '"password": password' not in bot,
    "generic bot copy": "اکانت مهاجرتی" not in bot and "V2Ray" not in bot,
    "my accounts untouched": '"/v1/subscriptions/me"' not in bot,
    "rc416 compatibility alias": '"/account-link/resolve-migrated"' in lookup,
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
