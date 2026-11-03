from types import SimpleNamespace

from app.services.payment_fulfillment_fast_path import (
    EARLY_DELIVERY_POLL_SECONDS,
    EARLY_DELIVERY_TIMEOUT_SECONDS,
    _credential_ready_for_early_delivery,
)
from app.telegram_purchase_delivery_fix_v1 import canonical_payment_event_key


def test_early_delivery_requires_active_committed_config():
    assert _credential_ready_for_early_delivery(None) is False
    assert _credential_ready_for_early_delivery(
        SimpleNamespace(is_active=False, config_text_encrypted="encrypted")
    ) is False
    assert _credential_ready_for_early_delivery(
        SimpleNamespace(is_active=True, config_text_encrypted=None)
    ) is False
    assert _credential_ready_for_early_delivery(
        SimpleNamespace(is_active=True, config_text_encrypted="")
    ) is False
    assert _credential_ready_for_early_delivery(
        SimpleNamespace(is_active=True, config_text_encrypted="encrypted-config")
    ) is True


def test_early_delivery_watcher_is_short_and_responsive():
    assert 0 < EARLY_DELIVERY_POLL_SECONDS <= 0.5
    assert 10 <= EARLY_DELIVERY_TIMEOUT_SECONDS <= 60


def test_early_and_final_notifications_share_same_canonical_key():
    payload = {
        "payment_id": 44,
        "order_id": 55,
        "subscription_id": 66,
    }

    early = canonical_payment_event_key(
        "payment-approved:44",
        "payment_approved",
        payload,
    )
    final = canonical_payment_event_key(
        "payment-auto-approved:any-old-shape",
        "payment_approved",
        payload,
    )

    assert early == final
    assert early == "payment-approved:order:55:payment:44:subscription:66"
