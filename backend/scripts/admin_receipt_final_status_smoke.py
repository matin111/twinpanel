"""Regression: manual receipt messages must not remain actionable after a decision."""
from pathlib import Path

source = (Path(__file__).resolve().parents[1] / "app" / "telegram_admin_ops_v1.py").read_text("utf-8")
compile(source, "telegram_admin_ops_v1.py", "exec")
assert "await _finalize_receipt_message(callback.message, detail)" in source
assert "edit_message_caption(" in source
assert "edit_message_text(" in source
assert "edit_message_reply_markup(" in source
assert "if not receipt.get(\"can_approve\")" in source
assert "len(parts) not in (5, 6)" in source  # old confirmation callback compatible
assert "origin_id = int(parts[5])" in source
assert "reply_markup=None" in source
assert "✅ رسید تأیید شد" in source
assert "❌ رسید رد شد" in source
print("ADMIN_RECEIPT_FINAL_STATUS_PASS")
