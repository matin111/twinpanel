from __future__ import annotations

import inspect

from app.routers.reseller_bot_orders_owned_v3 import (
    _bot_wallet_reference,
    _owned_bot_link,
    adjust_reseller_bot_wallet,
    reseller_bot_wallet_transactions,
    reseller_bot_wallets,
    router,
)


def main() -> None:
    paths = {route.path for route in router.routes}
    assert "/v1/reseller/bot-commerce/wallets" in paths
    assert "/v1/reseller/bot-commerce/wallets/{user_id}/transactions" in paths
    assert "/v1/reseller/bot-commerce/wallets/{user_id}/adjust" in paths

    scope_source = inspect.getsource(_owned_bot_link)
    adjust_source = inspect.getsource(adjust_reseller_bot_wallet)
    list_source = inspect.getsource(reseller_bot_wallets)
    tx_source = inspect.getsource(reseller_bot_wallet_transactions)

    assert "ResellerTelegramLink.reseller_id" in scope_source
    assert "ResellerTelegramLink.user_id" in scope_source
    assert "with_for_update" in scope_source
    assert "_wallet(db, int(user_id), lock=True)" in adjust_source
    assert "CustomerWalletTransaction.reference == reference" in adjust_source
    assert "balance_after < 0" in adjust_source
    assert 'kind="reseller_bot_adjustment"' in adjust_source
    assert "ResellerTelegramLink.reseller_id" in list_source
    assert "_owned_bot_link" in tx_source

    reference = _bot_wallet_reference(7, "wallet-smoke-123456")
    assert reference == "reseller-bot-wallet:7:wallet-smoke-123456"
    assert len(reference) <= 180

    print("RESELLER_BOT_WALLET_SMOKE_OK")


if __name__ == "__main__":
    main()
