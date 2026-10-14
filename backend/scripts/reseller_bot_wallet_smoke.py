from __future__ import annotations

import inspect
from pathlib import Path

from app.reseller_bot_wallet_menu_runtime import (
    _topup_method_marker,
    build_wallet_menu_router,
    wallet_main_keyboard,
)
from app.routers.reseller_bot_orders_owned_v3 import (
    _bot_wallet_reference,
    _owned_bot_link,
    _owned_wallet_transactions,
    adjust_reseller_bot_wallet,
    reseller_bot_wallet_transactions,
    reseller_bot_wallets,
    router,
)
from app.routers.reseller_bot_wallet_topups import (
    _method_parts,
    _topup_out,
    approve_reseller_bot_wallet_topup,
    reject_reseller_bot_wallet_topup,
    reseller_bot_wallet_topup_receipt,
    reseller_bot_wallet_topups,
    router as topup_router,
)


def main() -> None:
    paths = {route.path for route in router.routes}
    assert "/v1/reseller/bot-commerce/wallets" in paths
    assert "/v1/reseller/bot-commerce/wallets/{user_id}/transactions" in paths
    assert "/v1/reseller/bot-commerce/wallets/{user_id}/adjust" in paths

    topup_paths = {route.path for route in topup_router.routes}
    assert "/v1/reseller/bot-commerce/wallet-topups" in topup_paths
    assert "/v1/reseller/bot-commerce/wallet-topups/{topup_id}/receipt" in topup_paths
    assert "/v1/reseller/bot-commerce/wallet-topups/{topup_id}/approve" in topup_paths
    assert "/v1/reseller/bot-commerce/wallet-topups/{topup_id}/reject" in topup_paths

    scope_source = inspect.getsource(_owned_bot_link)
    ledger_source = inspect.getsource(_owned_wallet_transactions)
    adjust_source = inspect.getsource(adjust_reseller_bot_wallet)
    list_source = inspect.getsource(reseller_bot_wallets)
    tx_source = inspect.getsource(reseller_bot_wallet_transactions)
    topup_list_source = inspect.getsource(reseller_bot_wallet_topups)
    topup_out_source = inspect.getsource(_topup_out)
    receipt_source = inspect.getsource(reseller_bot_wallet_topup_receipt)
    approve_topup_source = inspect.getsource(approve_reseller_bot_wallet_topup)
    reject_topup_source = inspect.getsource(reject_reseller_bot_wallet_topup)

    assert "ResellerTelegramLink.reseller_id" in scope_source
    assert "ResellerTelegramLink.user_id" in scope_source
    assert "with_for_update" in scope_source
    assert "_wallet(db, int(user_id), lock=True)" in adjust_source
    assert "CustomerWalletTransaction.reference == reference" in adjust_source
    assert "balance_after < 0" in adjust_source
    assert 'kind="reseller_bot_adjustment"' in adjust_source
    assert "ResellerTelegramLink.reseller_id" in list_source
    assert "_owned_bot_link" in tx_source
    assert "_owned_wallet_transactions" in tx_source

    assert 'adjust_prefix = f"reseller-bot-wallet:{int(reseller_id)}:"' in ledger_source
    assert 'order_prefix = "reseller-bot-wallet-order:"' in ledger_source
    assert "ResellerBotOrder.reseller_id == int(reseller_id)" in ledger_source
    assert "ResellerBotOrder.customer_user_id == int(user_id)" in ledger_source

    assert _topup_method_marker(7, 11) == "reseller_card:7:11"
    marker_row = type("MarkerRow", (), {"method": "reseller_card:7:11"})()
    assert _method_parts(marker_row) == (7, 11)
    assert 'prefix = f"reseller_card:{int(reseller.id)}:%"' in topup_list_source
    assert '"receipt_uploaded": bool(row.receipt_file_marker)' in topup_out_source
    assert "_owned_topup" in receipt_source
    assert "receipt_file_marker" in receipt_source
    assert "lock=True" in approve_topup_source
    assert "receipt_file_marker" in approve_topup_source
    assert "عکس رسید برای این درخواست ثبت نشده است" in approve_topup_source
    assert 'f"reseller-bot-wallet:{int(reseller.id)}:topup:{int(row.id)}"' in approve_topup_source
    assert 'kind="reseller_bot_topup"' in approve_topup_source
    assert "_owned_topup" in reject_topup_source

    keyboard = wallet_main_keyboard()
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert "👛 کیف پول من" in labels
    wallet_router = build_wallet_menu_router(1)
    assert wallet_router.name == "reseller-wallet-menu-1"
    wallet_source = inspect.getsource(build_wallet_menu_router)
    assert 'F.text == "👛 کیف پول من"' in wallet_source
    assert 'F.data == "rwalletmenu:topup"' in wallet_source
    assert 'F.data.startswith("rwtm:")' in wallet_source
    assert "_topup_method_marker(reseller_id, int(method.id))" in wallet_source
    assert "عکس رسید پرداخت" in wallet_source
    assert "F.photo" in wallet_source
    assert "receipt_file_marker" in wallet_source
    assert "message.bot.download" in wallet_source
    assert 'row.status = "awaiting_review"' in wallet_source
    assert "کد پیگیری به‌تنهایی کافی نیست" in wallet_source

    repo_root = Path(__file__).resolve().parents[2]
    ui_path = repo_root / "components" / "reseller-bot-wallet-runtime.tsx"
    review_path = repo_root / "components" / "reseller-bot-wallet-topup-review.tsx"
    if ui_path.is_file():
        ui_source = ui_path.read_text(encoding="utf-8")
        assert "const [adjustKey,setAdjustKey]=useState(()=>idempotency())" in ui_source
        assert "idempotency_key:adjustKey" in ui_source
        assert "Keep adjustKey unchanged on failure" in ui_source
        assert "Boolean(result.duplicate)" in ui_source
        assert "ResellerBotWalletTopupReview" in ui_source
        assert review_path.is_file()
        review_source = review_path.read_text(encoding="utf-8")
        assert "receipt_uploaded" in review_source
        assert "مشاهده رسید" in review_source
        assert "/receipt`" in review_source
        print("RESELLER_BOT_WALLET_UI_CONTRACT_OK")
    else:
        print("RESELLER_BOT_WALLET_UI_CONTRACT_SKIPPED_BACKEND_RUNTIME")

    reference = _bot_wallet_reference(7, "wallet-smoke-123456")
    assert reference == "reseller-bot-wallet:7:wallet-smoke-123456"
    assert len(reference) <= 180

    print("RESELLER_BOT_WALLET_RECEIPT_PHOTO_OK")
    print("RESELLER_BOT_WALLET_MENU_TOPUP_OK")
    print("RESELLER_BOT_WALLET_SMOKE_OK")


if __name__ == "__main__":
    main()
