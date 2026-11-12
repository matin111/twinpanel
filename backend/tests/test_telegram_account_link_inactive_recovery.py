"""Regression tests for bot link recovery without touching the production DB.

Extract the actual SQLAlchemy query helper from the route module so the tests
run against an isolated SQLite database without app secrets, a Telegram bot or
a running TwinPanel server.
"""
from __future__ import annotations

import ast
import enum
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import DateTime, Enum, Integer, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "backend/app/routers/telegram_account_link_lookup.py").read_text(encoding="utf-8")


class Status(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    PENDING = "pending"
    CANCELED = "canceled"


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    __tablename__ = "test_bot_account_recovery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    account_username: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[Status] = mapped_column(Enum(Status), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def actual_recovery_query():
    module = ast.parse(SOURCE)
    function = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_lookup_single_recoverable_subscription"
    )
    states = next(
        node for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_LINK_RECOVERY_STATES"
                for target in node.targets)
    )
    namespace = {
        "Subscription": Subscription,
        "SubscriptionStatus": Status,
        "Session": Session,
    }
    exec(compile(ast.Module(body=[states, function], type_ignores=[]),
                 "<real_bot_account_lookup>", "exec"), namespace)
    return namespace["_lookup_single_recoverable_subscription"]


RECOVER = actual_recovery_query()


class TelegramAccountInactiveLinkRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def row(self, id: int, username: str, status: Status, user_id: int = 1,
            expires_at: datetime | None = None):
        sub = Subscription(id=id, user_id=user_id,
                           account_username=username, status=status,
                           expires_at=expires_at)
        self.db.add(sub)
        self.db.flush()
        return sub

    def recover(self, username: str, owner: int | None = None):
        criteria = [func.lower(Subscription.account_username) == username.casefold()]
        if owner is not None:
            criteria.append(Subscription.user_id == owner)
        return RECOVER(self.db, *criteria)

    def test_active_suspended_expired_return_existing_accounts(self):
        old = datetime.utcnow() - timedelta(days=10)
        future = datetime.utcnow() + timedelta(days=10)
        self.row(1, "ACTIVE-1", Status.ACTIVE, expires_at=future)
        self.row(2, "SUSPENDED-1", Status.SUSPENDED, expires_at=future)
        self.row(3, "EXPIRED-1", Status.EXPIRED, expires_at=old)
        self.assertEqual(self.recover("active-1").id, 1)
        self.assertEqual(self.recover("suspended-1").id, 2)
        self.assertEqual(self.recover("expired-1").id, 3)

    def test_active_row_with_past_expiry_is_still_link_recoverable(self):
        self.row(1, "old-date", Status.ACTIVE,
                 expires_at=datetime.utcnow() - timedelta(hours=1))
        self.assertEqual(self.recover("old-date").id, 1)

    def test_pending_and_canceled_are_never_returned(self):
        self.row(1, "pending-user", Status.PENDING)
        self.row(2, "canceled-user", Status.CANCELED)
        self.assertIsNone(self.recover("pending-user"))
        self.assertIsNone(self.recover("canceled-user"))

    def test_active_account_wins_over_archived_duplicate(self):
        self.row(1, "SameName", Status.EXPIRED)
        self.row(2, "samename", Status.ACTIVE)
        self.assertEqual(self.recover("SAMENAME").id, 2)

    def test_duplicate_active_or_inactive_rows_fail_closed(self):
        self.row(1, "dupe-active", Status.ACTIVE)
        self.row(2, "DUPE-ACTIVE", Status.ACTIVE)
        self.row(3, "dupe-old", Status.EXPIRED)
        self.row(4, "DUPE-OLD", Status.SUSPENDED)
        self.assertIsNone(self.recover("dupe-active"))
        self.assertIsNone(self.recover("dupe-old"))

    def test_owned_lookup_never_crosses_linked_user_boundary(self):
        self.row(1, "private", Status.SUSPENDED, user_id=1)
        self.assertIsNone(self.recover("private", owner=2))
        self.assertEqual(self.recover("private", owner=1).id, 1)

    def test_query_does_not_modify_status_or_expiry(self):
        date = datetime.utcnow() - timedelta(days=3)
        sub = self.row(1, "preserve", Status.EXPIRED, expires_at=date)
        self.assertIs(self.recover("preserve"), sub)
        self.assertEqual(sub.status, Status.EXPIRED)
        self.assertEqual(sub.expires_at, date)
        self.assertFalse(self.db.dirty)

    def test_telegram_handler_uses_recovered_link(self):
        bot_source = (ROOT / "backend/app/telegram_account_link_bot_original.py").read_text()
        self.assertIn('"/v1/telegram/account-link/resolve-username"', bot_source)
        self.assertIn("send_subscription_link_and_qr(", bot_source)
        route = SOURCE.split("def resolve_username_account_link(", 1)[1].split(
            "@router.post(", 1)[0]
        self.assertIn("_lookup_single_recoverable_subscription(", route)
        self.assertIn("_public_share_link(db, sub)", route)


if __name__ == "__main__":
    unittest.main()
