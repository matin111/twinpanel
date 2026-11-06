"""Central scheduling priority shared by migrated-account backfill workers.

Paid/new subscriptions always take precedence. Read-only DB checks: never
change order state, credentials or quotas to free a stalled queue.
"""
from datetime import datetime, timedelta

from ..database import SessionLocal
from ..fast_provision_job_models_v1 import FastProvisionJobV1
from ..reseller_bot_order_models import ResellerBotOrder
from ..store_models import StoreOrder


def new_account_work_has_priority() -> bool:
    cutoff = datetime.utcnow() - timedelta(minutes=45)
    with SessionLocal() as db:
        if db.query(StoreOrder.id).filter(
            StoreOrder.status == "provisioning",
            StoreOrder.created_at >= cutoff,
        ).first():
            return True
        if db.query(ResellerBotOrder.id).filter(
            ResellerBotOrder.status == "provisioning",
            ResellerBotOrder.created_at >= cutoff,
        ).first():
            return True
        return bool(db.query(FastProvisionJobV1.subscription_id).filter(
            FastProvisionJobV1.state.in_(("queued", "running", "retry")),
        ).first())
