from datetime import datetime, timedelta

from app.database import SessionLocal
from app.payment_models import PaymentIntent

# TWINPANEL_CLEANUP_MODEL_REGISTRY_V1_MAIN
# Register FK target tables before standalone ORM flush.
from . import models as _core_models
from . import store_models as _store_models



# TWINPANEL_MAIN_RECEIPT_RETENTION_5D_V1


def main():
    db = SessionLocal()

    try:
        cutoff = (
            datetime.utcnow()
            - timedelta(days=5)
        )

        rows = (
            db.query(PaymentIntent)
            .filter(
                PaymentIntent
                .receipt_telegram_file_id
                .isnot(None),

                PaymentIntent
                .receipt_submitted_at
                .isnot(None),

                PaymentIntent
                .receipt_submitted_at
                < cutoff,
            )
            .limit(2000)
            .all()
        )

        deleted = 0

        for row in rows:
            row.receipt_telegram_file_id = None
            row.receipt_submitted_at = None
            deleted += 1

        db.commit()

        print(
            "MAIN_RECEIPT_CLEANUP_OK",
            "deleted=",
            deleted,
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
