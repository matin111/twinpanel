from __future__ import annotations

import inspect
from pathlib import Path

from app.routers.reseller_bot_orders_owned_v3 import (
    _bot_wallet_reference,
    _owned_bot_link,
    _owned_wallet_transactions,
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
    ledger_source = inspect.getsource(_owned_wallet_transactions)
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
    assert "_owned_wallet_transactions" in tx_source

    # Ledger visibility must be reseller-scoped: manual adjustments carry the
    # reseller id and bot wallet purchases are accepted only when their order
    # belongs to the same reseller and customer.
    assert 'adjust_prefix = f"reseller-bot-wallet:{int(reseller_id)}:"' in ledger_source
    assert 'order_prefix = "reseller-bot-wallet-order:"' in ledger_source
    assert "ResellerBotOrder.reseller_id == int(reseller_id)" in ledger_source
    assert "ResellerBotOrder.customer_user_id == int(user_id)" in ledger_source

    # The UI must reuse the same key for retries. If the server committed and
    # the HTTP response disappeared, clicking submit again must be a duplicate,
    # not a second credit/debit.
    repo_root = Path(__file__).resolve().parents[2]
    ui_source = (
        repo_root / "components" / "reseller-bot-wallet-runtime.tsx"
    ).read_text(encoding="utf-8")
    assert "const [adjustKey,setAdjustKey]=useState(()=>idempotency())" in ui_source
    assert "idempotency_key:adjustKey" in ui_source
    assert "Keep adjustKey unchanged on failure" in ui_source
    assert "Boolean(result.duplicate)" in ui_source

    reference = _bot_wallet_reference(7, "wallet-smoke-123456")
    assert reference == "reseller-bot-wallet:7:wallet-smoke-123456"
    assert len(reference) <= 180

    print("RESELLER_BOT_WALLET_SMOKE_OK")


if __name__ == "__main__":
    main()
