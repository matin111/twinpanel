"""Prevent immediate-activation promises anywhere in Telegram renewal checkout."""
from pathlib import Path
import ast

APP = Path(__file__).resolve().parents[1] / "app"
RESERVED = "رزرو"
END = "پایان زمان یا حجم"
PATHS = (
    "telegram_subscription_import_bot_v1.py",
    "telegram_renewal_catalog_main_v1.py",
    "telegram_runtime_bot.py",
    "telegram_checkout_copy_v1.py",
)

def test_renewal_checkout_copy_has_reservation_timing():
    for path in PATHS:
        content = (APP / path).read_text(encoding="utf-8")
        ast.parse(content)
        assert RESERVED in content, path
    imported = (APP / PATHS[0]).read_text()
    normal = (APP / PATHS[1]).read_text()
    runtime = (APP / PATHS[2]).read_text()
    checkout = (APP / PATHS[3]).read_text()
    for content in (imported,normal,runtime,checkout):
        assert END in content
    for content in (imported,normal):
        assert "حجم و اعتبار پس از تأیید پرداخت به همین اکانت افزوده می‌شود" not in content
        assert "حجم و اعتبار پلن انتخابی پس از پرداخت به همین اکانت اضافه می‌شود" not in content
    assert "پس از پرداخت و تأیید، همین اشتراک تمدید می‌شود" not in imported
    assert "✅ <b>تمدید دوره بعد رزرو شد</b>" in runtime
    assert "🟢 دوره جدید فعال است" in runtime  # Only actual activation notification says active.
    assert "🕒 تمدید برای دوره بعد رزرو شد" in checkout

def test_release_guard_includes_all_renewal_copy_paths():
    workflow = (APP.parents[1] / ".github/workflows/publish-prebuilt-release.yml").read_text()
    for path in PATHS:
        assert f"backend/app/{path}" in workflow
