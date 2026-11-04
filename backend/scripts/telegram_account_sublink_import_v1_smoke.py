"""No-network smoke for the Telegram 'My Accounts' share-link import."""
from pathlib import Path
from urllib.parse import urlsplit
import ast
import re

ROOT = Path(__file__).resolve().parents[1] / "app"
api = (ROOT / "routers/telegram_subscription_import_v1.py").read_text("utf-8")
bot = (ROOT / "telegram_subscription_import_bot_v1.py").read_text("utf-8")
runtime = (ROOT / "telegram_runtime_bot.py").read_text("utf-8")
install = (ROOT / "telegram_account_link_bot.py").read_text("utf-8")
routes = (ROOT / "routers/__init__.py").read_text("utf-8")

for file in (api, bot, runtime, install, routes):
    compile(file, "<module>", "exec")

assert 'dependencies=[Depends(bot_guard)]' in api
assert 'db.get(TelegramUserLink, telegram_id)' in api
assert '_subscription_from_share_token(token, db)' in api
assert 'subscription_id=sub.id' in api
assert 'db.commit()' in api
assert 'sub.user_id =' not in api and 'subscription.user_id =' not in api
assert 'account-import/mine/' in runtime
assert 'subimp:add' in runtime and 'subimp:remove:' in bot
assert 'install_subscription_import(router, request_fn)' in install
assert '_telegram_subscription_import_v1_router' in routes

# Execute the actual URL parser with only its module-local import swapped
# for an inert fixed test host. No network calls, secrets, or DB required.
tree = ast.parse(api)
fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_extract_token")
snippet = ast.get_source_segment(api, fn)
assert snippet and "urlsplit" in snippet
snippet = snippet.replace(
    "from .account_delivery import subscription_base_url",
    "subscription_base_url = lambda db: 'https://sub.example.test'",
)

class Rejected(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code

ns = {"urlsplit": urlsplit, "re": re, "HTTPException": Rejected}
exec("from __future__ import annotations\n" + snippet, ns)
parse = ns["_extract_token"]
assert parse(None, "https://sub.example.test/v1/connect/valid-abc123") == "valid-abc123"
assert parse(None, "https://sub.example.test/v1/connect/valid-abc123?platform=karing") == "valid-abc123"
for invalid in (
    "http://sub.example.test/v1/connect/valid-abc123",
    "https://evil.example.test/v1/connect/valid-abc123",
    "https://sub.example.test.evil.com/v1/connect/valid-abc123",
    "https://sub.example.test@evil.example.test/v1/connect/valid-abc123",
    "https://sub.example.test/v1/connect/valid-abc123/multi/shadowtls",
    "https://sub.example.test/v1/connect/short",
    "https://sub.example.test/v1/connect/valid-abc123#not-supported",
):
    try:
        parse(None, invalid)
    except Rejected:
        pass
    else:
        raise AssertionError(f"Accepted invalid link: {invalid}")

print("TELEGRAM_ACCOUNT_SUBLINK_IMPORT_V1_SMOKE=PASS")
