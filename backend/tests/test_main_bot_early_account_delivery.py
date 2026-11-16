import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import payment_fulfillment_fast_path as service
from app.models import Subscription
from app.payment_models import PaymentIntent
from app.store_models import StoreOrder

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


def test_early_delivery_watcher_survives_slow_multinode_provisioning():
    assert 0 < EARLY_DELIVERY_POLL_SECONDS <= 0.5
    # The watcher is canceled at job completion, but must outlive the observed
    # 106-second multi-protocol provisioning path.
    assert 120 <= EARLY_DELIVERY_TIMEOUT_SECONDS <= 300


def test_slow_live_config_validation_does_not_block_api_loop():
    source = inspect.getsource(service._queue_main_bot_when_first_credential_ready)
    assert "await asyncio.to_thread(" in source
    assert "_try_queue_early_delivery_with_fresh_session" in source


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



def _exercise_delivery(*, order_status="provisioning", payment_status="approved",
                       link="https://sub.example.test/v1/connect/valid",
                       configs=True, share_code="test-share", username="test-account"):
    order = SimpleNamespace(
        id=361, user_id=16, subscription_id=4041, status=order_status,
    )
    payment = SimpleNamespace(
        id=298, order_id=361, user_id=16, status=payment_status,
    )
    subscription = SimpleNamespace(
        id=4041, user_id=16, status=SimpleNamespace(value="active"),
        account_username=username, share_code=share_code,
    )
    db = MagicMock()
    def by_id(model, value):
        if model is StoreOrder:
            return order
        if model is PaymentIntent:
            return payment
        if model is Subscription:
            return subscription
        raise AssertionError(f"unexpected model: {model}")
    db.get.side_effect = by_id
    credential = SimpleNamespace(is_active=True, config_text_encrypted="encrypted")
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = credential
    info = {
        "subscription_link": link,
        "account": {"username": username},
        "credentials": ([{"protocol": "wireguard", "config": {"endpoint": "test"}}]
                        if configs else []),
    }
    with (
        patch("app.routers.account_delivery._stored_info", return_value=info),
        patch.object(service, "_queue_ready_notification") as queue,
    ):
        result = service._try_queue_early_delivery_once(
            db, intent_id=298, order_id=361, user_id=16, amount_toman=100000
        )
        return result, queue


def test_verified_provisioning_account_delivers_before_all_protocols_finish():
    result, queue = _exercise_delivery()
    assert result == 4041
    queue.assert_called_once()
    assert queue.call_args.kwargs["provisioning"] is True


def test_finished_account_does_not_claim_partial_provisioning():
    result, queue = _exercise_delivery(order_status="fulfilled")
    assert result == 4041
    assert queue.call_args.kwargs["provisioning"] is False


def test_unverified_payment_cannot_send_account():
    result, queue = _exercise_delivery(payment_status="pending_payment")
    assert result is None
    queue.assert_not_called()


def test_missing_live_config_or_url_cannot_send_account():
    for kwargs in ({"configs": False},
                   {"link": ""},
                   {"link": "http://sub.example.test/link"},
                   {"link": "https://"},
                   {"share_code": ""},
                   {"username": ""}):
        result, queue = _exercise_delivery(**kwargs)
        assert result is None
        queue.assert_not_called()
