"""Check imported renewal selection reuses purchase catalog dimensions."""
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "app"
source = (root / "telegram_subscription_import_bot_v1.py").read_text("utf-8")
compile(source, "telegram_subscription_import_bot_v1.py", "exec")

for callback in ("subimprtype:", "subimprusers:", "subimprcat:", "subimprpage:"):
    assert callback in source, callback
for symbol in ("plan_subscription_type", "plan_user_count", "plan_category"):
    assert symbol in source, symbol
assert "start + 12 < len(matching)" in source
assert "subimprenewplan:" in source
assert "subimprenewconfirm:" in source
assert "renew-order" in source
assert "idempotency_key" in source
assert "callback.message.edit_text(" in source
assert "ابتدا نوع اشتراک" in source
assert "تعداد کاربر را انتخاب کنید" in source
assert "دسته‌بندی را انتخاب کنید" in source
print("IMPORTED_RENEWAL_CATEGORIZED=PASS")
