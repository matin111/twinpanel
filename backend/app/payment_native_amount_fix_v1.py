from __future__ import annotations

"""Compatibility fix for native-coin auto verification.

TRX/BNB intents store the exact payable amount in ``crypto_amount`` while the
legacy verifier reads ``crypto_amount_usdt``.  Keep the database schema and the
public payment contract unchanged; expose the native amount to the legacy
verifier as a clean in-memory committed value for the duration of verification.
"""

from sqlalchemy.orm.attributes import set_committed_value


def install() -> None:
    from .payment_models import PaymentIntent
    from .services import payment_native_crypto as native

    original = native.verify_native_crypto_intent
    if getattr(original, "_twinpanel_native_amount_fix_v1", False):
        return

    async def verify_native_crypto_intent_fixed(intent_id: int, db):
        intent = db.get(PaymentIntent, int(intent_id))
        if intent is None:
            return await original(intent_id, db)

        method = str(intent.method or "").strip().lower()
        native_method = method in {"trx_tron", "bnb_bsc"}
        needs_bridge = (
            native_method
            and intent.crypto_amount is not None
            and intent.crypto_amount_usdt is None
        )

        if not needs_bridge:
            return await original(intent_id, db)

        # set_committed_value changes the ORM view without marking the legacy
        # USDT column dirty, so the native amount is never persisted there.
        set_committed_value(
            intent,
            "crypto_amount_usdt",
            intent.crypto_amount,
        )

        try:
            return await original(intent_id, db)
        finally:
            try:
                current = db.get(PaymentIntent, int(intent_id))
                if current is not None and current.crypto_amount_usdt is not None:
                    set_committed_value(current, "crypto_amount_usdt", None)
            except Exception:
                pass

    verify_native_crypto_intent_fixed._twinpanel_native_amount_fix_v1 = True
    native.verify_native_crypto_intent = verify_native_crypto_intent_fixed
