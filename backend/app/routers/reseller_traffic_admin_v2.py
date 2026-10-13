from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models_reseller import (
    Reseller,
    ResellerTrafficPackage,
    ResellerTrafficTransaction,
)
from ..services.reseller_traffic_pool import restore_reseller_pool_subscriptions


router = APIRouter(
    prefix="/v1/admin/resellers",
    tags=["admin-reseller-traffic-v2"],
    dependencies=[Depends(require_admin)],
)

GB = 1024 ** 3


class TrafficAdjustV2In(BaseModel):
    traffic_gb: float
    description: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=120)


@router.get("/traffic-packages/all")
def list_reseller_traffic_packages_v2(
    db: Session = Depends(get_db),
):
    """Static route intentionally lives in the V2 router.

    The legacy reseller router also has /{reseller_id}; keeping this route in
    the earlier V2 router prevents `traffic-packages` from being interpreted as
    a reseller id and returning a 422 before package management can load.
    """
    rows = (
        db.query(ResellerTrafficPackage)
        .order_by(
            ResellerTrafficPackage.sort_order.asc(),
            ResellerTrafficPackage.id.asc(),
        )
        .all()
    )

    return [
        {
            "id": int(row.id),
            "title": row.title,
            "traffic_gb": int(row.traffic_gb or 0),
            "price_toman": int(row.price_toman or 0),
            "is_active": bool(row.is_active),
            "sort_order": int(row.sort_order or 0),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


@router.post("/{reseller_id}/traffic/adjust")
def adjust_reseller_traffic_v2(
    reseller_id: int,
    payload: TrafficAdjustV2In,
    db: Session = Depends(get_db),
):
    if payload.traffic_gb == 0:
        raise HTTPException(status_code=422, detail="مقدار حجم نمی‌تواند صفر باشد")

    if payload.idempotency_key:
        old = db.scalar(
            select(ResellerTrafficTransaction).where(
                ResellerTrafficTransaction.idempotency_key == payload.idempotency_key
            )
        )
        if old:
            return {
                "ok": True,
                "duplicate": True,
                "transaction_id": int(old.id),
                "traffic_balance_bytes": int(old.balance_after),
                "traffic_balance_gb": round(int(old.balance_after) / GB, 2),
            }

    reseller = db.scalar(
        select(Reseller)
        .where(Reseller.id == reseller_id)
        .with_for_update()
    )
    if not reseller:
        raise HTTPException(status_code=404, detail="نماینده پیدا نشد")

    delta = int(float(payload.traffic_gb) * GB)
    before = int(reseller.traffic_balance_bytes or 0)
    credit = int(reseller.traffic_credit_bytes or 0)
    after = before + delta

    if after < -credit:
        raise HTTPException(
            status_code=409,
            detail="موجودی حجم از اعتبار مجاز کمتر می‌شود",
        )

    reseller.traffic_balance_bytes = after
    reseller.updated_at = datetime.utcnow()

    tx = ResellerTrafficTransaction(
        reseller_id=reseller.id,
        bytes_amount=delta,
        balance_after=after,
        transaction_type="admin_traffic_credit" if delta > 0 else "admin_traffic_debit",
        description=payload.description,
        idempotency_key=payload.idempotency_key,
    )
    db.add(tx)
    db.flush()

    restored = {"restored": 0, "available": max(after + credit, 0)}
    if delta > 0 and before + credit <= 0 and after + credit > 0:
        restored = restore_reseller_pool_subscriptions(db, int(reseller.id))

    db.commit()
    db.refresh(tx)

    return {
        "ok": True,
        "transaction_id": int(tx.id),
        "traffic_delta_gb": round(delta / GB, 3),
        "traffic_balance_bytes": after,
        "traffic_balance_gb": round(after / GB, 2),
        "restored_subscriptions": int(restored.get("restored") or 0),
        "pricing_model": "volume_only",
    }
