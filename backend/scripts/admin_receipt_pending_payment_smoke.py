"""Regression: uploaded receipts in pending_payment reach Telegram chat review."""
from datetime import datetime, timedelta
from pathlib import Path
import ast
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1] / "app"
api = (root / "routers/telegram_admin_ops_v1.py").read_text()
push = (root / "services/telegram_admin_receipt_push.py").read_text()
worker = (root / "services/customer_maintenance.py").read_text()
for f in (api, push, worker):
    ast.parse(f)

# Extract the real status/time guards without importing the full application.
tree = ast.parse(api)
functions = [n for n in tree.body
             if isinstance(n, ast.FunctionDef) and n.name in ("_manual_purchase", "_manual_topup")]
constant = next(n for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "MANUAL_RECEIPT_GRACE_SECONDS" for t in n.targets))
namespace = {"datetime": datetime, "timedelta": timedelta,
             "PaymentIntent": object, "CustomerWalletTopup": object,
             "_purchase_needs_review": lambda row: row.status not in ("approved", "auto_verified", "rejected")}
exec(compile(ast.Module(body=[constant, *functions], type_ignores=[]), "<receipt-guard>", "exec"), namespace)
time_old = datetime.utcnow() - timedelta(seconds=35)
time_new = datetime.utcnow() - timedelta(seconds=5)
purchase = SimpleNamespace(status="pending_payment", receipt_telegram_file_id="local:receipt.jpg",
                           receipt_submitted_at=time_old, submitted_at=None)
wallet = SimpleNamespace(status="pending_payment", receipt_file_marker="local:wallet.jpg",
                         submitted_at=time_old, created_at=time_old)
assert namespace["_manual_purchase"](purchase)
assert namespace["_manual_topup"](wallet)
purchase.receipt_submitted_at = time_new
wallet.submitted_at = time_new
assert not namespace["_manual_purchase"](purchase)
assert not namespace["_manual_topup"](wallet)
purchase.receipt_submitted_at = time_old
wallet.submitted_at = time_old
purchase.status = "approved"
wallet.status = "approved"
assert not namespace["_manual_purchase"](purchase)
assert not namespace["_manual_topup"](wallet)
assert '"pending_payment"' in push
assert 'PaymentIntent.status.in_(statuses)' in push
assert 'CustomerWalletTopup.status.in_(statuses)' in push
assert 'or now - last_manual_receipt_push >= 10.0' in worker
assert '"✅ تأیید رسید"' in push and '"❌ رد رسید"' in push
print("TELEGRAM_RECEIPT_PENDING_PAYMENT_DELIVERY=PASS")
