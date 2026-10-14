from __future__ import annotations

import secrets

from app.customer_wallet_models import CustomerWalletTransaction, CustomerWalletTopup
from app.database import Base, SessionLocal, engine
from app.models import User
from app.models_reseller import Reseller, ResellerWalletTransaction
from app.services.wallet_payment_automation import credit_wallet_topup


def main() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    suffix = secrets.token_hex(5)

    try:
        user = User(
            email=f"reseller-wallet-{suffix}@example.com",
            password_hash="ci-not-a-real-login",
            full_name="Reseller Wallet Smoke",
            is_active=True,
        )
        db.add(user)
        db.flush()

        reseller = Reseller(
            owner_user_id=int(user.id),
            code=f"wallet-{suffix}",
            name="Wallet Smoke",
            wallet_balance=1_000,
            credit_limit=0,
            is_active=True,
        )
        db.add(reseller)
        db.flush()

        topup = CustomerWalletTopup(
            user_id=int(user.id),
            amount_toman=50_000,
            payable_amount_toman=50_000,
            method="card_to_card",
            status="awaiting_review",
        )
        db.add(topup)
        db.commit()
        db.refresh(topup)

        first = credit_wallet_topup(
            db,
            int(topup.id),
            source="ci-smoke",
        )

        db.refresh(reseller)
        assert first.get("ok") is True, first
        assert first.get("credited") is True, first
        assert first.get("wallet_type") == "reseller", first
        assert int(reseller.wallet_balance or 0) == 51_000

        reference = f"wallet-topup:{int(topup.id)}"
        reseller_tx = (
            db.query(ResellerWalletTransaction)
            .filter(ResellerWalletTransaction.idempotency_key == reference)
            .one()
        )
        assert int(reseller_tx.amount or 0) == 50_000
        assert int(reseller_tx.balance_after or 0) == 51_000

        customer_tx = (
            db.query(CustomerWalletTransaction)
            .filter(CustomerWalletTransaction.reference == reference)
            .first()
        )
        assert customer_tx is None

        second = credit_wallet_topup(
            db,
            int(topup.id),
            source="ci-smoke-retry",
        )
        db.refresh(reseller)
        assert second.get("ok") is True, second
        assert second.get("credited") is False, second
        assert second.get("already_approved") is True, second
        assert int(reseller.wallet_balance or 0) == 51_000

        count = (
            db.query(ResellerWalletTransaction)
            .filter(ResellerWalletTransaction.idempotency_key == reference)
            .count()
        )
        assert count == 1, count

        print("RESELLER_WALLET_CREDIT_IDEMPOTENCY_OK")

    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
