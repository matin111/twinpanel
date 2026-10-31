from __future__ import annotations

from pathlib import Path


path = Path("app/telegram_account_link_bot.py")
source = path.read_text(encoding="utf-8")
compile(source, str(path), "exec")

assert '"/v1/settings/branding"' in source
assert 'for field in ("brand_name", "site_title")' in source
assert 'DEFAULT_BRAND_NAME = "TwinPanel"' in source
assert "await _brand_name(request_fn)" in source
assert '"🤖 <b>Twin Panel</b>' not in source
assert '"ایمیل حساب Twin Panel را وارد کنید.' not in source
assert "await session_fn(" in source
assert "telegram_username=message.from_user.username" in source
assert "telegram_first_name=message.from_user.first_name" in source

print("TELEGRAM_BRAND_DISPLAY_NAME_V1_OK")
