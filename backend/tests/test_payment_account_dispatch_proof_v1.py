"""Tests for idempotent final account delivery after early payment messages."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import payment_fulfillment_fast_path as service
from app.routers import store
from app.store_models import StoreOrder
from app.payment_models import PaymentIntent
from app.telegram_notify_models import TelegramNotification


class AccountDeliveryProofTests(unittest.TestCase):
    def check(self, *, final_notice=False, marked=False, ready=True):
        now = datetime.utcnow()
        order = SimpleNamespace(
            id=360, user_id=8, subscription_id=4040, status="fulfilled",
            payment_method="card_to_card", amount_toman=200000,
            fulfilled_at=now-timedelta(minutes=1),
        )
        intent = SimpleNamespace(
            id=297, order_id=360, status="approved", payable_amount_toman=200000,
        )
        early = SimpleNamespace(
            kind="payment_approved", delivered_at=now-timedelta(minutes=2),
            payload={"order_id":360,"subscription_id":4040,
                     "payment_id":297,"account_delivery_sent":marked}
        )
        notices = [early]
        if final_notice:
            notices.append(SimpleNamespace(
                kind="payment_account_ready", delivered_at=None,
                payload={"order_id":360,"subscription_id":4040,"payment_id":297}
            ))
        db=MagicMock()
        q_orders=MagicMock()
        q_orders.filter.return_value.order_by.return_value.limit.return_value.all.return_value=[order]
        q_intents=MagicMock()
        q_intents.filter.return_value.order_by.return_value.first.return_value=intent
        q_notices=MagicMock()
        q_notices.filter.return_value.order_by.return_value.limit.return_value.all.return_value=notices
        def query(model):
            return {StoreOrder:q_orders,PaymentIntent:q_intents,
                    TelegramNotification:q_notices}[model]
        db.query.side_effect=query

        with (patch.object(service,"SessionLocal",return_value=db),
              patch.object(service,"queue_telegram_notification") as queue,
              patch.object(store,"_existing_delivery_snapshot",return_value={}),
              patch.object(store,"_delivery_ready_for_order",return_value=ready)):
            result=service.reconcile_early_payment_account_delivery_once()
            return result,queue,db

    def test_early_confirmation_gets_one_final_delivery(self):
        result,queue,db=self.check()
        self.assertEqual(result["queued"],1)
        self.assertEqual(queue.call_args.kwargs["kind"],"payment_account_ready")
        self.assertEqual(queue.call_args.kwargs["payload"]["subscription_id"],4040)
        db.commit.assert_called_once()

    def test_queued_final_notification_is_not_duplicated(self):
        result,queue,_=self.check(final_notice=True)
        self.assertEqual(result["queued"],0)
        queue.assert_not_called()

    def test_recorded_account_dispatch_is_not_duplicated(self):
        result,queue,_=self.check(marked=True)
        self.assertEqual(result["queued"],0)
        queue.assert_not_called()

    def test_incomplete_account_is_not_sent(self):
        result,queue,_=self.check(ready=False)
        self.assertEqual(result["queued"],0)
        queue.assert_not_called()


if __name__=="__main__":
    unittest.main()
