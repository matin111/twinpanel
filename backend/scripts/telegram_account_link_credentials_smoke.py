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
    "canonical username lookup": "func.lower(Subscription.account_username)" in lookup,
    "constant-time password compare": "hmac.compare_digest(" in lookup,
    "generic credential error": "نام کاربری یا رمز عبور اکانت اشتباه است" in lookup,
    "failed-attempt throttle": "_FAILURE_LIMIT = 6" in lookup and "status_code=429" in lookup,
    "canonical share URL reuse": "from .account_delivery import _share_url" in lookup,
    "password FSM state": "password = State()" in bot,
    "bot-only API call": '"/v1/telegram/account-link/resolve"' in bot and "bot_auth=True" in bot,
    "password sent for proof": '"password": password' in bot,
    "old owned-only scan removed": '"/v1/subscriptions/me"' not in bot,
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
