from sqlalchemy.orm import Session

from ..models import Subscription
from ..subscription_enforcement import (
    queue_subscription_enforcement,
)


def sync_subscription(
    db: Session,
    subscription_id: int,
):
    """
    Sync subscription with quota agents
    """

    sub = db.get(
        Subscription,
        subscription_id,
    )

    if not sub:
        return {
            "ok": False,
            "reason": "subscription_not_found",
        }


    try:
        enforcement = queue_subscription_enforcement(
            db,
            sub,
            command_type="restore_subscription",
            reason="provision_sync",
        )

        db.commit()

        return {
            "ok": True,
            "subscription_id": subscription_id,
            "enforcement": enforcement,
        }


    except Exception:
        db.rollback()
        raise
