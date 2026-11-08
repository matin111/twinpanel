"""Progressive central-node enrollment is set-based, guarded and safe."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from app.models import NodeStatus,NodeType,SubscriptionNode
from app.services import central_progressive_exit_admission_v1 as admission


def ready_db(*, visible=False, stage="verified_ready",
             listeners=16, attached=(1,2), expected=(1,2)):
    db=MagicMock()
    node=SimpleNamespace(
        id=14,node_type=NodeType.EXIT,status=NodeStatus.ONLINE,
        show_to_users=visible,retired_at=None)
    db.get.return_value=node
    job=SimpleNamespace(stage=stage,installed_protocols=listeners)
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value=job
    db.query.return_value.filter.return_value.all.return_value=[
        (i,) for i in attached]
    db.execute.return_value.rowcount=2
    desired=SimpleNamespace(subscription_ids=tuple(expected))
    return db,node,desired


class ProgressiveNodeAdmissionTests(unittest.TestCase):
    def test_visible_after_one_bulk_membership_transaction(self):
        db,node,desired=ready_db()
        with (
            patch.object(admission,"load_desired_state",return_value=desired),
            patch.object(admission,"require_valid_desired_state",
                         return_value=desired) as validate,
            patch.object(admission,"mark_central_node") as mark,
            patch.object(admission,"set_value") as settings,
        ):
            result=admission.admit_verified_exit(db,14)
        self.assertTrue(node.show_to_users)
        self.assertTrue(result["visible"])
        self.assertFalse(result["credentials_complete"])
        self.assertEqual(result["eligible_users"],2)
        db.commit.assert_called_once()
        validate.assert_called_once()
        mark.assert_called_once_with(db,14)
        settings.assert_called_once_with(
            db,"vpn.central_runtime.exit.14.progressive_admission","v1")
        sql=[str(c.args[0]) for c in db.execute.call_args_list]
        self.assertEqual(len(sql),3)
        self.assertIn("INSERT INTO subscription_nodes",sql[0])
        self.assertIn("ON CONFLICT",sql[0])
        self.assertIn("subscription_node_delivery_modes",sql[1])
        # No client private key or credential creation from Add Server.
        self.assertFalse(any("protocol_credentials" in x for x in sql))
        self.assertFalse(any("UPDATE subscriptions" in x for x in sql))

    def test_hidden_or_unverified_node_rejected_before_membership_write(self):
        for kwargs in (
            {"visible":True},{"stage":"installing_modern"},
            {"listeners":15},
        ):
            db,node,desired=ready_db(**kwargs)
            with self.assertRaisesRegex(RuntimeError,"NOT_.*READY|NOT_VERIFIED"):
                admission.admit_verified_exit(db,14)
            db.execute.assert_not_called()
            db.commit.assert_not_called()
            self.assertEqual(node.show_to_users,kwargs.get("visible",False))

    def test_missing_member_refuses_visibility_and_authority(self):
        db,node,desired=ready_db(attached=(1,),expected=(1,2))
        with (
            patch.object(admission,"load_desired_state",return_value=desired),
            patch.object(admission,"require_valid_desired_state",
                         return_value=desired),
            patch.object(admission,"mark_central_node") as mark,
        ):
            with self.assertRaisesRegex(RuntimeError,"MEMBERSHIP_COVERAGE_INCOMPLETE"):
                admission.admit_verified_exit(db,14)
            mark.assert_not_called()
        self.assertFalse(node.show_to_users)
        db.commit.assert_not_called()

    def test_quota_and_entitlements_fail_closed_before_write(self):
        db,node,desired=ready_db()
        with (
            patch.object(admission,"load_desired_state",return_value=desired),
            patch.object(admission,"require_valid_desired_state",
                         side_effect=RuntimeError("UNKNOWN_PURCHASED_PROTOCOL"))
        ):
            with self.assertRaisesRegex(RuntimeError,"UNKNOWN_PURCHASED_PROTOCOL"):
                admission.admit_verified_exit(db,14)
        db.execute.assert_not_called()
        db.commit.assert_not_called()

    def test_failed_detached_dispatch_hides_node_without_erasing_users(self):
        db,node,_=ready_db(visible=True)
        admission.hide_after_dispatch_failure(db,14)
        self.assertFalse(node.show_to_users)
        db.commit.assert_called_once()
        db.execute.assert_not_called()


if __name__=="__main__":
    unittest.main()
