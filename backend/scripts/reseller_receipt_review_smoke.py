from pathlib import Path
import ast

root = Path(__file__).resolve().parents[1] / "app"
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
