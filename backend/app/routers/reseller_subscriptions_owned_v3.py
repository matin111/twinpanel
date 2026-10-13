from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_reseller
from ..models_reseller import Reseller
from ..reseller_owned_plans import owned_plan_by_backing
from . import reseller_portal as legacy


router = APIRouter(
    prefix="/v1/reseller",
    tags=["reseller-subscriptions-owned-v3"],
)


@router.get("/subscriptions")
def reseller_subscriptions_owned(
    reseller: Reseller = Depends(require_reseller),
    db: Session = Depends(get_db),
):
    rows = legacy.reseller_subscriptions(
        reseller=reseller,
        db=db,
    )

    for row in rows:
        try:
            backing_plan_id = int(row.get("plan_id") or 0)
        except Exception:
            backing_plan_id = 0

        if not backing_plan_id:
            continue

        owned = owned_plan_by_backing(
            db,
            int(reseller.id),
            backing_plan_id,
            active_only=False,
        )

        if owned:
            row["reseller_plan_id"] = int(owned.id)
            row["plan_name"] = owned.title
            row["plan_source"] = "reseller"
            row["buy_price_toman"] = 0
            row["profit_toman"] = int(row.get("sell_price_toman") or 0)

    return rows
