"""Read-only central node materialization audit contracts."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.central_node_stage_audit_v1 import verify_coverage


def fake_db(active, attached, requested, credentials):
    db=MagicMock()
    db.get.return_value=SimpleNamespace(retired_at=None,show_to_users=False)
    groups=[]
    for values in (active,attached,requested,credentials):
        query=MagicMock()
        query.filter.return_value.all.return_value=values
        groups.append(query)
    db.query.side_effect=groups
    return db


class StageCoverageAuditTests(unittest.TestCase):
    def test_complete_actual_node_item(self):
        cred=SimpleNamespace(subscription_id=1,protocol="openvpn",is_active=True)
        db=fake_db([(1,)],[(1,)],[(1,"openvpn")],[cred])
        with (patch("app.central_node_stage_audit_v1.ad._autosync_credential_items",
                    return_value=[{"node_id":14}]),
              patch("app.central_node_stage_audit_v1.ad._autosync_item_node_id",
                    side_effect=lambda item:item["node_id"])):
            report=verify_coverage(db,14)
        self.assertTrue(report["ok"])
        self.assertEqual(report["ready_protocol_pairs"],1)
        db.commit.assert_not_called()

    def test_unmaterialized_protocol_blocks_readiness(self):
        cred=SimpleNamespace(subscription_id=1,protocol="wireguard",is_active=True)
        db=fake_db([(1,)],[(1,)],[(1,"wireguard")],[cred])
        with patch("app.central_node_stage_audit_v1.ad._autosync_credential_items",
                   return_value=[]):
            result=verify_coverage(db,14)
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_by_protocol"],{"wireguard":1})

    def test_unattached_or_unentitled_subscriptions_block(self):
        db=fake_db([(1,),(2,)],[(1,)],[(1,"openvpn")],[])
        result=verify_coverage(db,14)
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_node_memberships"],1)
        self.assertEqual(result["subscriptions_without_entitlements"],1)

    def test_no_published_node_can_pass(self):
        db=fake_db([],[],[],[])
        db.get.return_value.show_to_users=True
        with self.assertRaisesRegex(RuntimeError,"HIDDEN"):
            verify_coverage(db,14)


if __name__=="__main__":
    unittest.main()
