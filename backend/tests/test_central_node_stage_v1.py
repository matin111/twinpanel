"""Guardrails for the single central node staging entrypoint."""
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace

from scripts import twinpanel_central_node_stage_v1 as stage
from app.models import NodeStatus, NodeType


def desired_state(count):
    return SimpleNamespace(
        count=count, pair_count=count, fingerprint="0"*64,
        entitled_pairs=((1,"sudoku"),) if count else (),
        invalid_protocols=(), without_entitlements=(),
    )


class CentralNodeStageTests(unittest.TestCase):
    def test_bulk_adapters_include_xray_and_no_individual_worker(self):
        self.assertEqual(len(stage.ADAPTERS), 10)
        self.assertFalse(any("backfill" in name for name in stage.ADAPTERS))
        self.assertTrue(all("central_" in name and ("bulk" in name or "shared" in name)
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
        db.commit.assert_not_called()

    def test_dry_run_does_not_write_or_start_protocols(self):
        fake = MagicMock()
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "load_desired_state", return_value=desired_state(1183)),
              patch.object(stage, "establish_hidden_memberships") as insert,
              patch.object(stage, "reconcile_runtime_families", new_callable=AsyncMock) as invoke):
            session.return_value.__enter__.return_value = db
            self.assertEqual(stage.run(14, 3000, False), 0)
            insert.assert_not_called()
            invoke.assert_not_awaited()
            db.commit.assert_not_called()


    def test_unhealthy_protocols_block_membership_changes(self):
        fake = MagicMock()
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "load_desired_state", return_value=desired_state(1183)),
              patch.object(stage, "verify_new_exit_readiness", new_callable=AsyncMock, return_value={"ok": False}),
              patch.object(stage, "establish_hidden_memberships") as insert):
            session.return_value.__enter__.return_value = db
            with self.assertRaisesRegex(RuntimeError, "PROTOCOLS_NOT_READY"):
                stage._run_locked(14, 3000, True)
            insert.assert_not_called()
            db.commit.assert_not_called()


    def test_all_registry_protocols_have_bounded_adapters(self):
        self.assertEqual(set(stage.MISSING_BULK_PROTOCOLS), set())
        self.assertEqual(
            set(stage.ALL_PROTOCOL_KEYS),
            set(stage.BULK_PROTOCOLS) | set(stage.MISSING_BULK_PROTOCOLS),
        )


    def test_all_service_families_reconciled_once_after_snapshot(self):
        fake = MagicMock()
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "load_desired_state", return_value=desired_state(3)),
              patch.object(stage, "verify_new_exit_readiness", new_callable=AsyncMock, return_value={"ok": True}),
              patch.object(stage, "establish_hidden_memberships", return_value=3),
              patch.object(stage, "verify_coverage", return_value={"ok": True}),
              patch.object(stage, "ensure_shared_binary", new_callable=AsyncMock,
                           return_value={"ok":True,"binary_ready":True}) as bootstrap,
              patch.object(stage, "reconcile_runtime_families", new_callable=AsyncMock) as invoke):
            session.return_value.__enter__.return_value = db
            invoke.return_value = {"ok": True, "failed": [], "succeeded": []}
            self.assertEqual(stage._run_locked(14, 3000, True), 0)
            invoke.assert_awaited_once()
            bootstrap.assert_awaited_once()
            self.assertEqual(db.commit.call_count,2)


    def test_missing_shared_binary_blocks_all_writes_before_runtime(self):
        fake = MagicMock()
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        with (patch.object(stage,"SessionLocal") as session,
              patch.object(stage,"load_desired_state",return_value=desired_state(1206)),
              patch.object(stage,"verify_new_exit_readiness",new_callable=AsyncMock,
                           return_value={"ok":True}),
              patch.object(stage,"ensure_shared_binary",new_callable=AsyncMock,
                           side_effect=RuntimeError("SUDOKU_SHARED_TARGET_BINARY_UNRECOGNIZED")),
              patch.object(stage,"establish_hidden_memberships") as insert,
              patch.object(stage,"reconcile_runtime_families",new_callable=AsyncMock) as run):
            session.return_value.__enter__.return_value=db
            with self.assertRaisesRegex(RuntimeError,"SUDOKU_SHARED_TARGET_BINARY_UNRECOGNIZED"):
                stage._run_locked(14,3000,True)
            insert.assert_not_called()
            run.assert_not_awaited()
            db.commit.assert_not_called()


    def test_listener_probe_runs_without_row_lock(self):
        fake = MagicMock()
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        calls_during_health = []
        async def health(session, node_id):
            calls_during_health.extend(session.get.call_args_list)
            return {"ok": False}
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "load_desired_state", return_value=desired_state(3)),
              patch.object(stage, "verify_new_exit_readiness", health)):
            session.return_value.__enter__.return_value = db
            with self.assertRaisesRegex(RuntimeError, "PROTOCOLS_NOT_READY"):
                stage._run_locked(14, 3000, True)
        self.assertEqual(len(calls_during_health), 1)
        self.assertNotIn("with_for_update", calls_during_health[0].kwargs)


    def test_new_subscriptions_mid_apply_trigger_bounded_resnapshot(self):
        with patch.object(stage,"_run_locked",side_effect=[
            RuntimeError("CENTRAL_NODE_DESIRED_STATE_CHANGED_DURING_APPLY"),0
        ]) as apply:
            self.assertEqual(stage.run(14,3000,True),0)
            self.assertEqual(apply.call_count,2)
            apply.assert_any_call(14,3000,True)

    def test_delta_coverage_retries_without_per_user_queue(self):
        with patch.object(stage,"_run_locked",side_effect=[3,0]) as apply:
            self.assertEqual(stage.run(14,3000,True),0)
            self.assertEqual(apply.call_count,2)

    def test_other_runtime_failures_are_not_retried(self):
        with patch.object(stage,"_run_locked",return_value=2) as apply:
            self.assertEqual(stage.run(14,3000,True),2)
            apply.assert_called_once()

    def test_continuous_writes_fail_closed_after_three_snapshots(self):
        with patch.object(stage,"_run_locked",
                          side_effect=RuntimeError("CENTRAL_NODE_DESIRED_STATE_CHANGED_DURING_APPLY")) as apply:
            with self.assertRaisesRegex(RuntimeError,"STILL_CHANGING"):
                stage.run(14,3000,True)
            self.assertEqual(apply.call_count,3)

    def test_shared_sudoku_adapter_replaces_per_user_units(self):
        self.assertIn("twinpanel_central_sudoku_shared_v2.py",stage.ADAPTERS)
        self.assertNotIn("twinpanel_central_sudoku_node_bulk_v1.py",stage.ADAPTERS)


if __name__ == "__main__":
    unittest.main()
