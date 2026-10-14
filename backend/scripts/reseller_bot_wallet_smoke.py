from __future__ import annotations

import inspect
from pathlib import Path

from app.reseller_bot_wallet_menu_runtime import (
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
    approve_reseller_bot_wallet_topup,
    reject_reseller_bot_wallet_topup,
    router as topup_router,
)


def main() -> None:
    paths = {route.path for route in router.routes}
    assert "/v1/reseller/bot-commerce/wallets" in paths
    assert "/v1/reseller/bot-commerce/wallets/{user_id}/transactions" in paths
    assert "/v1/reseller/bot-commerce/wallets/{user_id}/adjust" in paths

    topup_paths = {route.path for route in topup_router.routes}
    assert "/v1/reseller/bot-commerce/wallet-topups" in topup_paths
    assert "/v1/reseller/bot-commerce/wallet-topups/{topup_id}/approve" in topup_paths
    assert "/v1/reseller/bot-commerce/wallet-topups/{topup_id}/reject" in topup_paths

    scope_source = inspect.getsource(_owned_bot_link)
    ledger_source = inspect.getsource(_owned_wallet_transactions)
    adjust_source = inspect.getsource(adjust_reseller_bot_wallet)
    list_source = inspect.getsource(reseller_bot_wallets)
    tx_source = inspect.getsource(reseller_bot_wallet_transactions)
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

    # Ledger visibility must be reseller-scoped: manual adjustments carry the
    # reseller id and bot wallet purchases are accepted only when their order
    # belongs to the same reseller + customer.
    assert 'adjust_prefix = f"reseller-bot-wallet:{int(reseller_id)}:"' in ledger_source
    assert 'order_prefix = "reseller-bot-wallet-order:"' in ledger_source
    assert "ResellerBotOrder.reseller_id == int(reseller_id)" in ledger_source
    assert "ResellerBotOrder.customer_user_id == int(user_id)" in ledger_source

    # Card-to-card top-up approval is row-locked and idempotent. Only linked
    # customers of the current reseller can be credited or rejected.
    assert "lock=True" in approve_topup_source
    assert 'reference = f"reseller-bot-wallet-topup:' in approve_topup_source
    assert 'kind="reseller_bot_topup"' in approve_topup_source
    assert "_owned_topup" in reject_topup_source

    # The Telegram bot must expose wallet as a first-class main-menu feature.
    keyboard = wallet_main_keyboard()
    labels = [button.text for row in keyboard.keyboard for button in row]
    assert "👛 کیف پول من" in labels
    wallet_router = build_wallet_menu_router(1)
    assert wallet_router.name == "reseller-wallet-menu-1"
    wallet_source = inspect.getsource(build_wallet_menu_router)
    assert 'F.text == "👛 کیف پول من"' in wallet_source
    assert 'F.data == "rwalletmenu:topup"' in wallet_source
    assert 'F.data.startswith("rwtm:")' in wallet_source
    assert 'method=f"reseller_card:' in wallet_source
    assert 'status = "awaiting_review"' in wallet_source

    # Full-repository CI also validates the frontend retry contract. Production
    # backend runtimes intentionally do not contain the Next.js /components
    # tree, so backend-only runtime smoke must not fail just because that UI
    # source is absent there.
    repo_root = Path(__file__).resolve().parents[2]
    ui_path = repo_root / "components" / "reseller-bot-wallet-runtime.tsx"
    if ui_path.is_file():
        ui_source = ui_path.read_text(encoding="utf-8")
        assert "const [adjustKey,setAdjustKey]=useState(()=>idempotency())" in ui_source
        assert "idempotency_key:adjustKey" in ui_source
        assert "Keep adjustKey unchanged on failure" in ui_source
        assert "Boolean(result.duplicate)" in ui_source
        print("RESELLER_BOT_WALLET_UI_CONTRACT_OK")
    else:
        print("RESELLER_BOT_WALLET_UI_CONTRACT_SKIPPED_BACKEND_RUNTIME")

    reference = _bot_wallet_reference(7, "wallet-smoke-123456")
    assert reference == "reseller-bot-wallet:7:wallet-smoke-123456"
    assert len(reference) <= 180

    print("RESELLER_BOT_WALLET_MENU_TOPUP_OK")
    print("RESELLER_BOT_WALLET_SMOKE_OK")


if __name__ == "__main__":
    main()
