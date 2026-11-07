"""Central stage systemd dispatch tests: never SSH/DB mutate inside API."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models import NodeStatus, NodeType
from app.services import central_node_stage_launcher_v1 as launcher


class CentralStageLauncherTests(unittest.TestCase):
    def db(self, *, hidden=True, stage="verified_ready", node=True):
        db=MagicMock()
        if node:
            db.get.return_value=SimpleNamespace(
                retired_at=None,node_type=NodeType.EXIT,
                status=NodeStatus.ONLINE,show_to_users=not hidden,
            )
        else:
            db.get.return_value=None
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            SimpleNamespace(stage=stage) if stage else None
        )
        return db

    def test_hidden_verified_exit_launches_one_systemd_unit(self):
        db=self.db()
        with (patch.object(launcher.shutil, "which", return_value="/usr/bin/systemd-run"),
              patch.object(launcher, "STAGE", MagicMock(is_file=MagicMock(return_value=True))),
              patch.object(launcher.subprocess, "run") as run):
            run.return_value.returncode=0
            status=launcher.launch(db,14)
        self.assertTrue(status["scheduled"])
        self.assertFalse(status["automatic_publication"])
        command=run.call_args.args[0]
        self.assertIn("--unit=twinpanel-central-node-stage-14",command)
        self.assertIn("--no-block",command)
        self.assertEqual(command[-5:],
                         ["--limit","3000","--apply","--confirm-node-id","14"])
        self.assertFalse(run.call_args.kwargs.get("shell",False))
        db.commit.assert_not_called()

    def test_published_or_unverified_nodes_not_launched(self):
        for db in (self.db(hidden=False), self.db(stage="installing_modern"),
                   self.db(node=False)):
            with self.subTest(db=db):
                with patch.object(launcher.subprocess,"run") as run:
                    with self.assertRaises(launcher.CentralStageLaunchError):
                        launcher.launch(db,14)
                    run.assert_not_called()

    def test_missing_systemd_fails_closed(self):
        with patch.object(launcher.shutil,"which",return_value=None):
            with self.assertRaisesRegex(launcher.CentralStageLaunchError,
                                        "RUNNER_UNAVAILABLE"):
                launcher.launch(self.db(),14)

    def test_systemd_rejection_not_reported_as_started(self):
        with (patch.object(launcher.shutil,"which",return_value="/usr/bin/systemd-run"),
              patch.object(launcher, "STAGE", MagicMock(is_file=MagicMock(return_value=True))),
              patch.object(launcher.subprocess,"run") as run):
            run.return_value.returncode=1
            with self.assertRaisesRegex(launcher.CentralStageLaunchError,
                                        "DISPATCH_REJECTED"):
                launcher.launch(self.db(),14)


if __name__=="__main__":
    unittest.main()
