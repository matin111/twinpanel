from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import (
    ProtocolCredential,
    Subscription,
    SubscriptionNode,
    SubscriptionProtocol,
    SubscriptionStatus,
)
from ..quota_models import QuotaCursor, QuotaDevice, QuotaSession, QuotaUsageEvent
from ..subscription_enforcement import queue_subscription_enforcement


router = APIRouter(
    prefix="/v1/subscriptions",
    tags=["subscriptions"],
    dependencies=[Depends(require_admin)],
)


# TWINPANEL_SUBSCRIPTION_HARD_DELETE_V1
# DELETE means real deletion. Capture revoke/session identity first, then remove
# quota rows which use RESTRICT foreign keys, then remove the Subscription row.
# Legacy rows already marked CANCELED by the previous soft-delete implementation
# are deleted without creating a duplicate revoke operation.
@router.delete("/{subscription_id}")
def hard_delete_subscription(
    subscription_id: int,
    db: Session = Depends(get_db),
):
    sub = db.get(Subscription, int(subscription_id))
    if sub is None:
        raise HTTPException(status_code=404, detail="اشتراک پیدا نشد")

    deleted_id = int(sub.id)
    was_canceled = sub.status == SubscriptionStatus.CANCELED
    enforcement = {
        "operation_id": None,
        "commands": [],
        "commands_created": 0,
        "devices_updated": 0,
    }

    try:
        if not was_canceled:
            enforcement = queue_subscription_enforcement(
                db,
                sub,
                command_type="revoke_subscription",
                reason="subscription_hard_deleted",
            )
            # Persist command rows in the same transaction, but do not commit
            # until the database deletion has also succeeded.
            db.flush()

        # quota_usage_events references subscriptions and quota_devices with
        # ON DELETE RESTRICT. Delete it before sessions/devices. Explicit child
        # deletion keeps behavior deterministic even when FK cascade settings
        # differ in lightweight test databases.
        deleted_usage_events = (
            db.query(QuotaUsageEvent)
            .filter(QuotaUsageEvent.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_sessions = (
            db.query(QuotaSession)
            .filter(QuotaSession.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_cursors = (
            db.query(QuotaCursor)
            .filter(QuotaCursor.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_devices = (
            db.query(QuotaDevice)
            .filter(QuotaDevice.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_credentials = (
            db.query(ProtocolCredential)
            .filter(ProtocolCredential.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_protocols = (
            db.query(SubscriptionProtocol)
            .filter(SubscriptionProtocol.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )
        deleted_nodes = (
            db.query(SubscriptionNode)
            .filter(SubscriptionNode.subscription_id == deleted_id)
            .delete(synchronize_session=False)
        )

        db.delete(sub)
        db.flush()

        if db.get(Subscription, deleted_id) is not None:
            raise RuntimeError("subscription row still exists after hard delete")

        db.commit()

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="حذف کامل اشتراک انجام نشد: " + str(exc)[:500],
        ) from exc

    return {
        "ok": True,
        "subscription_id": deleted_id,
        "deleted": True,
        "status": "deleted",
        "previously_canceled": bool(was_canceled),
        "enforcement": (
            "already_revoked"
            if was_canceled
            else (
                "queued"
                if int(enforcement.get("commands_created") or 0) > 0
                else "no_credentials"
            )
        ),
        **enforcement,
        "deleted_rows": {
            "quota_usage_events": int(deleted_usage_events),
            "quota_sessions": int(deleted_sessions),
            "quota_cursors": int(deleted_cursors),
            "quota_devices": int(deleted_devices),
            "protocol_credentials": int(deleted_credentials),
            "subscription_protocols": int(deleted_protocols),
            "subscription_nodes": int(deleted_nodes),
            "subscriptions": 1,
        },
        "message": "اشتراک به‌طور کامل حذف شد",
    }
