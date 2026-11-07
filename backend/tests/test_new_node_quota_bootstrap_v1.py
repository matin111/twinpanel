"""Regressions for fresh Exit quota bootstrap without a missing shell script."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models import NodeType
from app.services import new_node_quota_bootstrap_v1 as quota


def _db(*, visible=False, member=False, node_type=NodeType.EXIT):
    db=MagicMock()
    db.get.return_value=SimpleNamespace(
        id=15, retired_at=None, node_type=node_type, show_to_users=visible,
    )
    db.query.return_value.filter.return_value.first.return_value = (
        (123,) if member else None
    )
    return db


def _canonical_result():
    return {
        "ok": True, "devices": 0,
        "payload": {"version": 5, "node_id": 15,
                    "telemetry_policy": {"fail_closed": True}, "devices": []},
    }


class FreshExitQuotaBootstrapTests(unittest.TestCase):
    def test_fresh_hidden_exit_uses_canonical_fail_closed_quota(self):
        db=_db()
        with patch.object(quota, "sync_node_config",
                          return_value=_canonical_result()) as builder:
            self.assertEqual(
                quota.bootstrap_fresh_hidden_exit_quota(db,15),
                {"ok":True,"mode":"agent_pull","devices":0},
            )
            builder.assert_called_once_with(db,15,precomputed_devices=[])

    def test_existing_assigned_users_must_not_be_replaced_with_empty_quota(self):
        db=_db(member=True)
        with patch.object(quota,"sync_node_config") as builder:
            result=quota.bootstrap_fresh_hidden_exit_quota(db,15)
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"],"existing_node_memberships")
            builder.assert_not_called()

    def test_published_node_is_not_new_install(self):
        db=_db(visible=True)
        with patch.object(quota,"sync_node_config") as builder:
            self.assertFalse(quota.bootstrap_fresh_hidden_exit_quota(db,15)["ok"])
            builder.assert_not_called()

    def test_non_exit_refused(self):
        db=_db(node_type=NodeType.IRAN)
        with patch.object(quota,"sync_node_config") as builder:
            self.assertFalse(quota.bootstrap_fresh_hidden_exit_quota(db,15)["ok"])
            builder.assert_not_called()

    def test_telemetry_must_fail_closed(self):
        db=_db()
        bad=_canonical_result()
        bad["payload"]["telemetry_policy"]["fail_closed"]=False
        with patch.object(quota,"sync_node_config",return_value=bad):
            result=quota.bootstrap_fresh_hidden_exit_quota(db,15)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"],"quota_config_invalid")

    def test_exception_fails_closed_without_disclosing_secrets(self):
        db=_db()
        with patch.object(quota,"sync_node_config",
                          side_effect=RuntimeError("private password string")):
            result=quota.bootstrap_fresh_hidden_exit_quota(db,15)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"],"RuntimeError")
        self.assertNotIn("password",str(result))


if __name__=="__main__":
    unittest.main()
