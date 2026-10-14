from pathlib import Path
import ast
import sys

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

root = backend_root / "app"
review_path = root / "reseller_bot_review.py"
learning_path = root / "telegram_learning_center.py"

review = review_path.read_text(encoding="utf-8")
learning = learning_path.read_text(encoding="utf-8")

ast.parse(review)
ast.parse(learning)

assert "TelegramUserLink" in review
assert "owner_user_id" in review
assert "awaiting_review" in review
assert "rmanager:approve:" in review
assert "rmanager:reject:" in review
assert "approve_order" in review
assert "reject_order" in review
assert "register_reseller_review_handlers" in learning

print("RESELLER_RECEIPT_REVIEW_SMOKE_OK")

from scripts.discount_schema_bootstrap_smoke import main as discount_schema_bootstrap_smoke
from scripts.reseller_bot_payment_callbacks_smoke import main as reseller_bot_payment_callbacks_smoke
from scripts.reseller_bot_wallet_smoke import main as reseller_bot_wallet_smoke
from scripts.reseller_owned_order_approval_smoke import main as reseller_owned_order_approval_smoke
from scripts.reseller_usage_pool_smoke import main as reseller_usage_pool_smoke
from scripts.reseller_route_precedence_smoke import main as reseller_route_precedence_smoke
from scripts.reseller_wallet_credit_smoke import main as reseller_wallet_credit_smoke
from scripts.wallet_receipt_route_smoke import main as wallet_receipt_route_smoke

discount_schema_bootstrap_smoke()
reseller_bot_payment_callbacks_smoke()
reseller_bot_wallet_smoke()
reseller_owned_order_approval_smoke()
reseller_usage_pool_smoke()
reseller_route_precedence_smoke()
reseller_wallet_credit_smoke()
wallet_receipt_route_smoke()
