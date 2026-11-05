"""Regression for main-bot wallet checkout. No real purchases or wallet changes."""
import ast
from pathlib import Path
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

root = Path(__file__).resolve().parents[1] / "app"
bot = (root / "telegram_purchase_bot.py").read_text(encoding="utf-8")
wallet = (root / "routers/customer_wallet.py").read_text(encoding="utf-8")
store = (root / "routers/store.py").read_text(encoding="utf-8")
payments = (root / "routers/payments.py").read_text(encoding="utf-8")
worker = (root / "services/payment_fulfillment_fast_path.py").read_text(encoding="utf-8")

for path, code in (("bot",bot),("wallet",wallet),("store",store),("payments",payments),("worker",worker)):
    ast.parse(code, filename=path)
tree = ast.parse(bot)
keyboard_fn = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == "payment_methods_keyboard")
env = {"InlineKeyboardButton": InlineKeyboardButton,
       "InlineKeyboardMarkup": InlineKeyboardMarkup}
exec(compile(ast.Module(body=[keyboard_fn], type_ignores=[]), "bot_keyboard", "exec"), env)
kb = env["payment_methods_keyboard"](12345, [
    {"id": "card_to_card", "title": "کارت به کارت"},
])
buttons = [(button.text, button.callback_data) for row in kb.inline_keyboard for button in row]
assert ("💰 پرداخت از کیف پول", "shop:wallet:preview:12345") in buttons
assert ("💳 کارت به کارت", "shop:pay:12345:card_to_card") in buttons
wallet_only = env["payment_methods_keyboard"](12345, [])
assert any(b.callback_data == "shop:wallet:preview:12345" for row in wallet_only.inline_keyboard for b in row)

for required in (
    'shop:wallet:preview:', 'shop:wallet:confirm:', 'shop:wallet:back:',
    '✅ تأیید و پرداخت از کیف پول',
    '/v1/wallet/orders/{order_id}/pay',
    '/v1/wallet/me',
    'balance >= amount',
    'method_data.get("methods")',
):
    assert required in bot, required

for required in (
    'StoreOrder.user_id == int(user.id)',
    '.with_for_update()',
    'wallet.balance_toman = balance - amount',
    'CustomerWalletTransaction(',
    'reference = f"store-order-wallet:{order_id}"',
    'already_paid',
    'order.payment_method == "wallet"',
    'if order.status != "pending_payment"',
    'external_payment',
    'background_tasks.add_task(fulfill_wallet_order_background, order_id)',
):
    assert required in wallet, required

assert 'if not intent and order.payment_method != "wallet"' in store
assert '"wallet-purchase:order:' in store
assert 'if order.status != "pending_payment"' in payments
assert 'async def fulfill_wallet_order_background' in worker
assert 'async def process_wallet_paid_orders_once' in worker
assert 'wallet_result = await process_wallet_paid_orders_once()' in worker
assert 'StoreOrder.payment_method == "wallet"' in worker
print("MAIN_BOT_WALLET_CHECKOUT_SMOKE=PASS")
