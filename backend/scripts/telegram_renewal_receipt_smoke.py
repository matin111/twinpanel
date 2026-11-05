"""Static regression for renewal card receipt handler and legacy crypto TXID path."""
from pathlib import Path

source = (Path(__file__).resolve().parents[1] / "app" / "telegram_runtime_bot.py").read_text("utf-8")
compile(source, "telegram_runtime_bot.py", "exec")

start = source.index("def renewal_proof_keyboard(")
end = source.index("async def _telegram_session_token(", start)
keyboard = source[start:end]
assert "📷 ارسال رسید پرداخت" in keyboard
assert "method == \"card_to_card\"" in keyboard
assert "renewproof:" in keyboard

start = source.index("async def renewal_proof_start(")
end = source.index("@router.message(\n    F.text == \"👤 حساب من\"", start)
flow = source[start:end]
assert "RenewalPaymentState.receipt" in flow
assert "RenewalPaymentState.proof" in flow
assert "@router.message(RenewalPaymentState.receipt)" in flow
assert '"/receipt"' not in flow or '/receipt' in flow
assert 'payload={"telegram_file_id": file_id}' in flow
assert 'payload={"txid": value}' in flow
assert "message.photo[-1].file_id" in flow
assert "message.document.file_id" in flow
assert "await state.clear()" in flow
assert 'payload["tracking_code"] = value' not in flow
print("TELEGRAM_RENEWAL_RECEIPT=PASS")
