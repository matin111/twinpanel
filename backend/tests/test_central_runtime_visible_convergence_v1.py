"""New central runtime is the only owner of published new-generation Exits."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from app.models import NodeStatus,NodeType
from app.services import central_runtime_ownership_v1 as owner
from app.services import central_runtime_visible_convergence_v1 as auto
from app.services import central_node_stage_launcher_v1 as launcher


def node(node_id,visible=True):
    return SimpleNamespace(
        id=node_id,node_type=NodeType.EXIT,status=NodeStatus.ONLINE,
        retired_at=None,show_to_users=visible,
    )


class OwnershipTests(unittest.TestCase):
    def test_unregistered_published_exit_not_central(self):
        db=MagicMock()
        with patch.object(owner,"get_value",return_value=""):
            self.assertFalse(owner.allow_central_node(db,node(14,True)))
            self.assertTrue(owner.allow_central_node(db,node(14,False)))

    def test_registered_published_exit_has_central_authority(self):
        db=MagicMock()
        with patch.object(owner,"get_value",return_value="v1"):
            self.assertTrue(owner.allow_central_node(db,node(14,True)))
        with patch.object(owner,"set_value") as setter:
            owner.mark_central_applied(db,14,"a"*64)
            setter.assert_called_once_with(
                db,owner.last_applied_key(14),"a"*64)

    def test_hidden_stage_marker_rejected_invalid_fingerprint(self):
        with self.assertRaisesRegex(ValueError,"INVALID_FINGERPRINT"):
            owner.mark_central_applied(MagicMock(),14,"not-a-sha256")


class VisibleConvergenceTests(unittest.TestCase):
    def _run(self,last):
        db=MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value=[
            node(14),node(99)
        ]
        session=MagicMock()
        session.return_value.__enter__.return_value=db
        with (
            patch.object(auto,"SessionLocal",session),
            patch.object(auto,"is_central_node",side_effect=lambda db,n:n==14),
            patch.object(auto,"load_desired_state",
                         return_value=SimpleNamespace(fingerprint="b"*64)),
            patch.object(auto,"require_valid_desired_state",side_effect=lambda val,**_:val),
            patch.object(auto,"last_applied",return_value=last),
            patch.object(auto,"launch",return_value={"scheduled":True}) as launch,
        ):
            result=auto.run_once()
        return result,launch,db

    def test_changed_state_dispatches_one_detached_daemon_job(self):
        result,launch,db=self._run("a"*64)
        self.assertEqual(result["dispatched"],[14])
        self.assertEqual(result["up_to_date"],[])
        launch.assert_called_once_with(db,14)
        db.rollback.assert_called()

    def test_unchanged_state_never_dispatches(self):
        result,launch,_=self._run("b"*64)
        self.assertEqual(result["up_to_date"],[14])
        launch.assert_not_called()

    def test_legacy_visible_nodes_are_not_sent_to_central_engine(self):
        result,_,_=self._run("b"*64)
        self.assertNotIn(99,result["up_to_date"])
        self.assertNotIn(99,result["dispatched"])

    def test_published_registered_exit_launches_despite_old_job_label(self):
        db=MagicMock()
        db.get.return_value=node(14,True)
        with patch.object(launcher,"is_central_node",return_value=True):
            launcher.ensure_launchable(db,14)
        db.query.assert_not_called()

    def test_unregistered_visible_exit_never_launches(self):
        db=MagicMock()
        db.get.return_value=node(14,True)
        with (
            patch.object(launcher,"is_central_node",return_value=False),
            patch.object(owner,"get_value",return_value=""),
        ):
            with self.assertRaises(launcher.CentralStageLaunchError):
                launcher.ensure_launchable(db,14)


if __name__=="__main__":
    unittest.main()
