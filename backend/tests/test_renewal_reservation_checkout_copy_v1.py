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


def test_new_purchase_and_renewal_have_distinct_payment_outcomes():
    """A new purchase is provisioned promptly, never held until an old cycle ends."""
    import importlib.util
    path = APP / "telegram_checkout_copy_v1.py"
    spec = importlib.util.spec_from_file_location("telegram_checkout_copy_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for receipt in (False, True):
        purchase = module.proof_success("در انتظار بررسی", renewal=False, receipt=receipt)
        renewal = module.proof_success("در انتظار بررسی", renewal=True, receipt=receipt)
        assert "خرید" in purchase
        assert "رزرو" not in purchase
        assert "دوره فعلی" not in purchase
        assert "تمدید" in renewal
        assert "رزرو" in renewal
        assert END in renewal

    new_purchase_pending = module.wallet_success_text(12, renewal=False, fulfilled=False)
    new_purchase_ready = module.wallet_success_text(12, renewal=False, fulfilled=True)
    next_cycle = module.wallet_success_text(12, renewal=True, fulfilled=False)
    assert "در حال آماده‌سازی" in new_purchase_pending
    assert "اشتراک شما آماده است" in new_purchase_ready
    assert "رزرو" not in new_purchase_pending + new_purchase_ready
    assert "رزرو" in next_cycle and END in next_cycle
    assert "خرید" in module.choose_payment_text(renewal=False)
    assert "تمدید" in module.choose_payment_text(renewal=True)
