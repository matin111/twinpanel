"""Guardrails for the single central node staging entrypoint."""
import unittest
from unittest.mock import MagicMock, patch

from scripts import twinpanel_central_node_stage_v1 as stage
from app.models import NodeStatus, NodeType


class CentralNodeStageTests(unittest.TestCase):
    def test_bulk_adapters_include_xray_and_no_individual_worker(self):
        self.assertEqual(len(stage.ADAPTERS), 4)
        self.assertFalse(any("backfill" in name for name in stage.ADAPTERS))
        self.assertTrue(all("central_" in name and "bulk" in name
                            for name in stage.ADAPTERS))

    def test_xray_batches_use_100_not_global_user_limit(self):
        cmd = stage.adapter_command(
            "twinpanel_central_xray_node_bulk_v1.py", 14, 3000, True
        )
        self.assertEqual(cmd[cmd.index("--limit") + 1], "100")
        self.assertIn("--all", cmd)
        self.assertEqual(cmd[-2:], ["--confirm-node-id", "14"])

    def test_other_adapters_preserve_global_limit(self):
        cmd = stage.adapter_command(stage.ADAPTERS[0], 14, 3000, True)
        self.assertEqual(cmd[cmd.index("--limit") + 1], "3000")

    def test_hidden_node_required(self):
        fake = MagicMock()
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = True
        db = MagicMock()
        db.get.return_value = fake
        with patch.object(stage, "SessionLocal") as session:
            session.return_value.__enter__.return_value = db
            with self.assertRaisesRegex(RuntimeError, "HIDDEN_ONLINE_EXIT"):
                stage.run(14, 3000, False)
        db.execute.assert_not_called()

    def test_dry_run_does_not_write_or_start_protocols(self):
        fake = MagicMock()
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "eligible_count", return_value=1183),
              patch.object(stage, "establish_hidden_memberships") as insert,
              patch.object(stage.subprocess, "run") as invoke):
            session.return_value.__enter__.return_value = db
            self.assertEqual(stage.run(14, 3000, False), 0)
            insert.assert_not_called()
            invoke.assert_not_called()
            db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
