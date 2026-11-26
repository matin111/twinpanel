"""Auth dependency must not pin PostgreSQL request pool over slow awaits."""
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app import deps


class AuthReadTransactionTests(TestCase):
    def test_valid_user_releases_read_transaction_before_endpoint(self):
        user=SimpleNamespace(id=7,is_active=True,role=deps.UserRole.ADMIN)
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=user
        with patch.object(deps,"decode_access_token",return_value="7"):
            value=deps.get_current_user("sample-token",db)
        self.assertIs(value,user)
        db.commit.assert_called_once_with()
        db.close.assert_not_called()

    def test_invalid_user_does_not_commit(self):
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=None
        with patch.object(deps,"decode_access_token",return_value="7"):
            with self.assertRaises(HTTPException):
                deps.get_current_user("sample-token",db)
        db.commit.assert_not_called()

    def test_reseller_releases_read_transaction(self):
        reseller=SimpleNamespace(id=9,is_active=True,owner_user_id=7)
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=reseller
        value=deps.require_reseller(SimpleNamespace(id=7),db)
        self.assertIs(value,reseller)
        db.commit.assert_called_once_with()

    def test_disabled_reseller_does_not_commit(self):
        reseller=SimpleNamespace(id=9,is_active=False,owner_user_id=7)
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=reseller
        with self.assertRaises(HTTPException):
            deps.require_reseller(SimpleNamespace(id=7),db)
        db.commit.assert_not_called()


if __name__=="__main__":
    main()
