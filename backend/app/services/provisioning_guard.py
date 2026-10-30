from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..database import engine


# TWINPANEL_SUBSCRIPTION_PROVISIONING_GUARD_V1
#
# Provisioning performs remote SSH work and may live for tens of seconds. The
# guard must therefore not depend on the request's ORM transaction: holding the
# lock on a dedicated AUTOCOMMIT connection prevents concurrent provisioning
# for the same subscription without creating a long-lived database transaction.


@dataclass
class SubscriptionProvisioningGuard:
    subscription_id: int
    _conn: Connection | None = None
    _locked: bool = False

    @property
    def key(self) -> str:
        return f"twinpanel:subscription-provision:{int(self.subscription_id)}"

    def acquire(self) -> bool:
        if self._conn is not None:
            raise RuntimeError("provisioning guard already acquired")

        conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            locked = bool(
                conn.execute(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                    {"key": self.key},
                ).scalar()
            )
        except Exception:
            conn.close()
            raise

        if not locked:
            conn.close()
            return False

        self._conn = conn
        self._locked = True
        return True

    def release(self) -> None:
        conn = self._conn
        self._conn = None
        if conn is None:
            return

        try:
            if self._locked:
                conn.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                    {"key": self.key},
                )
        finally:
            self._locked = False
            conn.close()

    def __enter__(self) -> "SubscriptionProvisioningGuard":
        if not self.acquire():
            raise BlockingIOError("subscription provisioning already in progress")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
