from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path

from app.database import SessionLocal
from app.payment_models import PaymentIntent

# TWINPANEL_CLEANUP_MODEL_REGISTRY_V1_MAIN
# Register FK target tables before standalone ORM flush.
from . import models as _core_models
from . import store_models as _store_models


# TWINPANEL_MAIN_RECEIPT_RETENTION_7D_V2
RETENTION_DAYS = 7
RECEIPT_ROOT = Path(
    os.getenv(
        "TWINPANEL_PAYMENT_RECEIPT_DIR",
        "/var/lib/twinpanel/payment-receipts",
    )
).resolve()


def _local_receipt_path(marker: str) -> Path | None:
    marker = str(marker or "").strip()

    if not marker.startswith("local:"):
        return None

    filename = marker[6:].strip()

    if (
        not filename
        or filename != Path(filename).name
        or ".." in filename
    ):
        return None

    candidate = (RECEIPT_ROOT / filename).resolve()

    try:
        candidate.relative_to(RECEIPT_ROOT)
    except ValueError:
        return None

    return candidate


def cleanup_receipts_once() -> dict:
    """Remove payment receipt access and local files after seven days.

    Financial/payment history is preserved. Only the uploaded receipt itself
    and its submitted timestamp are cleared so the admin panel no longer
    exposes a receipt after the retention window.
    """

    db = SessionLocal()

    try:
        cutoff = (
            datetime.utcnow()
            - timedelta(days=RETENTION_DAYS)
        )

        rows = (
            db.query(PaymentIntent)
            .filter(
                PaymentIntent.receipt_telegram_file_id.isnot(None),
                PaymentIntent.receipt_submitted_at.isnot(None),
                PaymentIntent.receipt_submitted_at < cutoff,
            )
            .limit(5000)
            .all()
        )

        cleared = 0
        local_deleted = 0
        local_delete_failed = 0

        for row in rows:
            marker = str(
                row.receipt_telegram_file_id or ""
            ).strip()

            local_path = _local_receipt_path(marker)

            if local_path is not None:
                try:
                    if local_path.exists():
                        local_path.unlink()
                        local_deleted += 1
                except OSError:
                    local_delete_failed += 1

            row.receipt_telegram_file_id = None
            row.receipt_submitted_at = None
            cleared += 1

        db.commit()

        return {
            "ok": True,
            "retention_days": RETENTION_DAYS,
            "cleared": cleared,
            "local_deleted": local_deleted,
            "local_delete_failed": local_delete_failed,
            "cutoff": cutoff.isoformat() + "Z",
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def main():
    result = cleanup_receipts_once()

    print(
        "MAIN_RECEIPT_CLEANUP_OK",
        result,
        flush=True,
    )


if __name__ == "__main__":
    main()
