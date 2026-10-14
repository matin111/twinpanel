from __future__ import annotations

from sqlalchemy import inspect

# Register referenced parent tables before creating the discount tables. This
# keeps the helper safe when it is invoked by the standalone reseller bot
# process instead of the FastAPI process.
from . import models as _models  # noqa: F401
from . import models_reseller as _models_reseller  # noqa: F401
from .database import engine as default_engine
from .discount_models import DiscountCode, DiscountRedemption


REQUIRED_DISCOUNT_TABLES = (
    "discount_codes",
    "discount_redemptions",
)


def ensure_discount_schema(*, bind=None) -> dict[str, bool]:
    """Create missing discount tables without touching existing data.

    SQLAlchemy ``create_all`` only sees models that were imported before it
    runs. Historically TwinPanel imported the discount router after the global
    ``create_all`` call, so existing installations could have discount code
    logic available while ``discount_redemptions`` was still absent.

    This helper is intentionally narrow: it creates only the two discount
    tables, uses ``checkfirst=True``, and never drops or rewrites a table.
    """

    target = bind or default_engine

    DiscountCode.__table__.create(
        bind=target,
        checkfirst=True,
    )
    DiscountRedemption.__table__.create(
        bind=target,
        checkfirst=True,
    )

    present = set(inspect(target).get_table_names())
    state = {
        table_name: table_name in present
        for table_name in REQUIRED_DISCOUNT_TABLES
    }

    missing = [name for name, exists in state.items() if not exists]
    if missing:
        raise RuntimeError(
            "discount schema bootstrap incomplete: " + ", ".join(missing)
        )

    return state
