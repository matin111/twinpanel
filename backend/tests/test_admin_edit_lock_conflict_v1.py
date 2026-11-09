"""Isolated regression for transient PostgreSQL admin-edit lock conflicts.

Never opens a real database or enqueues customer provisioning.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.routers.subscription_admin_edit_fast_v1 import (
    _commit_admin_edit,
    _is_retryable_lock_timeout,
)


def db_error(code):
    original = SimpleNamespace(pgcode=code)
    return OperationalError("UPDATE subscriptions ...", {}, original)


class AdminEditLockHandlingTests(unittest.TestCase):
    def test_postgresql_lock_conflict_codes_only(self):
        for code in ("55P03", "40P01"):
            with self.subTest(code=code):
                self.assertTrue(_is_retryable_lock_timeout(db_error(code)))
        for code in ("23505", "40001", "08006", "", None):
            with self.subTest(code=code):
                self.assertFalse(_is_retryable_lock_timeout(db_error(code)))

    def test_lock_timeout_rolls_back_once_and_returns_retryable_503(self):
        for code in ("55P03", "40P01"):
            with self.subTest(code=code):
                session = Mock()
                session.commit.side_effect = db_error(code)
                with self.assertRaises(HTTPException) as raised:
                    _commit_admin_edit(session)
                self.assertEqual(raised.exception.status_code, 503)
                self.assertEqual(raised.exception.headers["Retry-After"], "2")
                session.commit.assert_called_once()
                session.rollback.assert_called_once()

    def test_non_lock_database_errors_are_not_swallowed(self):
        session = Mock()
        session.commit.side_effect = db_error("23505")
        with self.assertRaises(OperationalError):
            _commit_admin_edit(session)
        session.rollback.assert_called_once()
        session.commit.assert_called_once()

    def test_success_commits_once_without_rollback(self):
        session = Mock()
        _commit_admin_edit(session)
        session.commit.assert_called_once()
        session.rollback.assert_not_called()

    def test_dml_lock_timeouts_are_also_handled_by_route(self):
        from pathlib import Path
        route = (Path(__file__).resolve().parents[1] /
                 "app/routers/subscription_admin_edit_fast_v1.py").read_text(
                     encoding="utf-8")
        # A DML delete/update can fail before the explicit commit. Preserve
        # the outer transaction-level classifier and rollback.
        self.assertIn("except OperationalError as exc:\n        # DML may hit lock_timeout", route)
        self.assertIn("_is_retryable_lock_timeout(exc)", route)
        self.assertIn('"Retry-After": "2"', route)

    def test_no_orig_database_error_not_misclassified(self):
        exc = OperationalError("UPDATE", {}, RuntimeError("network unavailable"))
        self.assertFalse(_is_retryable_lock_timeout(exc))


if __name__ == "__main__":
    unittest.main()
