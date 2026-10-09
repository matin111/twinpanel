from datetime import datetime, timedelta

from app.database import SessionLocal
from app.reseller_bot_order_models import ResellerBotOrder

# TWINPANEL_CLEANUP_MODEL_REGISTRY_V1_RESELLER
# Register FK target tables before standalone ORM flush.
from . import models as _core_models
from . import models_reseller as _reseller_models



# TWINPANEL_RESELLER_RECEIPT_RETENTION_5D_V1
RETENTION_DAYS = 5


def main():
    db = SessionLocal()

    try:
        cutoff = (
            datetime.utcnow()
            - timedelta(days=RETENTION_DAYS)
        )

        rows = (
            db.query(ResellerBotOrder)
            .filter(
                ResellerBotOrder.receipt_telegram_file_id.isnot(
                    None
                ),
                ResellerBotOrder.submitted_at.isnot(
                    None
                ),
                ResellerBotOrder.submitted_at
                < cutoff,
            )
            .all()
        )

        deleted = 0

        for row in rows:
            row.receipt_telegram_file_id = None
            deleted += 1

        if deleted:
            db.commit()
        else:
            db.rollback()

        print(
            "RECEIPT_CLEANUP_OK",
            "retention_days=",
            RETENTION_DAYS,
            "deleted=",
            deleted,
            "cutoff=",
            cutoff.isoformat(),
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
