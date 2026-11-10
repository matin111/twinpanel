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
    def setUp(self):
        # Existing full-node contract mocks have no staged progress table.
        # Partial-only scope and fail-closed behavior have dedicated tests.
        scoped=patch.object(stage, "node_supported_protocols",
                            return_value=frozenset(stage.ALL_PROTOCOL_KEYS))
        scoped.start()
        self.addCleanup(scoped.stop)

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
              patch.object(stage, "verify_new_exit_readiness", new_callable=AsyncMock, return_value={"ok": True, "ready_protocols": list(stage.ALL_PROTOCOL_KEYS)}),
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


    def test_first_detached_stage_keeps_progressively_visible_exit_visible(self):
        fake=MagicMock()
        fake.id=14
        fake.retired_at=None
        fake.node_type=NodeType.EXIT
        fake.status=NodeStatus.ONLINE
        fake.show_to_users=True
        db=MagicMock()
        db.get.return_value=fake
        with (patch.object(stage,"SessionLocal") as session,
              patch.object(stage,"allow_central_node",return_value=True),
              patch.object(stage,"load_desired_state",return_value=desired_state(3)),
              patch.object(stage,"verify_new_exit_readiness",
                           new_callable=AsyncMock,return_value={"ok": True, "ready_protocols": list(stage.ALL_PROTOCOL_KEYS)}),
              patch.object(stage,"ensure_shared_binary",
                           new_callable=AsyncMock,return_value={"ok":True}),
              patch.object(stage,"establish_hidden_memberships",return_value=0),
              patch.object(stage,"reconcile_runtime_families",
                           new_callable=AsyncMock,return_value={
                               "ok":True,"failed":[],"succeeded":[]}),
              patch.object(stage,"verify_coverage",return_value={"ok":True}),
              patch.object(stage,"mark_central_node") as mark,
              patch.object(stage,"mark_central_applied") as applied):
            session.return_value.__enter__.return_value=db
            rc=stage._run_locked(14,3000,True)
        self.assertEqual(rc,0)
        self.assertTrue(fake.show_to_users)
        mark.assert_called_once_with(db,14)
        applied.assert_called_once()
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
        async def health(session, node_id, **kwargs):
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
        with (patch.object(stage,"_run_locked",side_effect=[
            RuntimeError("CENTRAL_NODE_DESIRED_STATE_CHANGED_DURING_APPLY"),0
        ]) as apply,
              patch.object(stage,"missing_runtime_families",
                           return_value=(stage.FAMILIES[0],))):
            self.assertEqual(stage.run(14,3000,True),0)
            self.assertEqual(apply.call_count,2)
            apply.assert_any_call(14,3000,True)
            apply.assert_any_call(14,3000,True,
                                  families=(stage.FAMILIES[0],))

    def test_delta_coverage_retries_without_per_user_queue(self):
        with (patch.object(stage,"_run_locked",side_effect=[3,0]) as apply,
              patch.object(stage,"missing_runtime_families",
                           return_value=(stage.FAMILIES[1],))):
            self.assertEqual(stage.run(14,3000,True),0)
            self.assertEqual(apply.call_count,2)
            apply.assert_any_call(14,3000,True,
                                  families=(stage.FAMILIES[1],))

    def test_other_runtime_failures_are_not_retried(self):
        with patch.object(stage,"_run_locked",return_value=2) as apply:
            self.assertEqual(stage.run(14,3000,True),2)
            apply.assert_called_once()

    def test_continuous_writes_fail_closed_after_three_snapshots(self):
        with (patch.object(stage,"_run_locked",
                          side_effect=RuntimeError("CENTRAL_NODE_DESIRED_STATE_CHANGED_DURING_APPLY")) as apply,
              patch.object(stage,"missing_runtime_families",
                           return_value=(stage.FAMILIES[0],))):
            with self.assertRaisesRegex(RuntimeError,"STILL_CHANGING"):
                stage.run(14,3000,True)
            self.assertEqual(apply.call_count,3)


    def test_snapshot_churn_already_covered_does_not_reapply_all_families(self):
        fake = MagicMock()
        fake.id = 14
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        before = desired_state(3)
        after = SimpleNamespace(**{**vars(before), "count": 4,
                                   "pair_count": 4, "fingerprint": "1" * 64})
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "load_desired_state",
                           side_effect=[before, before, after]),
              patch.object(stage, "verify_new_exit_readiness", new_callable=AsyncMock,
                           return_value={"ok": True}),
              patch.object(stage, "ensure_shared_binary", new_callable=AsyncMock,
                           return_value={"ok": True}),
              patch.object(stage, "establish_hidden_memberships", return_value=4),
              patch.object(stage, "verify_coverage",
                           return_value={"ok": True, "missing_protocol_pairs": 0,
                                         "missing_node_memberships": 0}),
              patch.object(stage, "reconcile_runtime_families", new_callable=AsyncMock,
                           return_value={"ok": True, "failed": [], "succeeded": []}) as apply,
              patch.object(stage, "mark_central_applied") as mark):
            session.return_value.__enter__.return_value = db
            self.assertEqual(stage._run_locked(14, 3000, True), 0)
            apply.assert_awaited_once()
            self.assertEqual(mark.call_args.args[2], after.fingerprint)

    def test_snapshot_churn_with_missing_coverage_still_blocks_publishing(self):
        fake = MagicMock()
        fake.id = 14
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        before = desired_state(3)
        after = SimpleNamespace(**{**vars(before), "count": 4,
                                   "pair_count": 4, "fingerprint": "1" * 64})
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "load_desired_state",
                           side_effect=[before, before, after]),
              patch.object(stage, "verify_new_exit_readiness", new_callable=AsyncMock,
                           return_value={"ok": True}),
              patch.object(stage, "ensure_shared_binary", new_callable=AsyncMock,
                           return_value={"ok": True}),
              patch.object(stage, "establish_hidden_memberships", return_value=4),
              patch.object(stage, "verify_coverage",
                           return_value={"ok": False, "missing_protocol_pairs": 16,
                                         "missing_node_memberships": 1}),
              patch.object(stage, "reconcile_runtime_families", new_callable=AsyncMock,
                           return_value={"ok": True, "failed": [], "succeeded": []}),
              patch.object(stage, "mark_central_applied") as mark):
            session.return_value.__enter__.return_value = db
            with self.assertRaisesRegex(RuntimeError, "CHANGED_DURING_APPLY"):
                stage._run_locked(14, 3000, True)
            mark.assert_not_called()


    def test_delta_selector_only_returns_missing_daemon_families(self):
        fake = MagicMock()
        fake.id = 14
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        audit = {"ok": False, "missing_by_protocol": {"wireguard": 4,
                                                       "openvpn": 0},
                 "subscriptions_without_entitlements": 0,
                 "unknown_protocols": []}
        with (patch.object(stage, "SessionLocal") as session,
              # A stable, previously acknowledged Sudoku-only whitelist
              # must not be re-staged for unrelated protocol/membership drift.
              patch.object(stage, "desired_sudoku_fingerprint", return_value="d"*64),
              patch.object(stage, "last_sudoku_applied", return_value="d"*64),
              patch.object(stage, "load_desired_state",
                           return_value=desired_state(3)),
              patch.object(stage, "verify_coverage", return_value=audit)):
            session.return_value.__enter__.return_value = db
            names = [family.name for family in
                     stage.missing_runtime_families(14, 3000)]
        self.assertEqual(names, ["wireguard"])

    def test_delta_selector_membership_only_does_not_restart_daemons(self):
        fake = MagicMock()
        fake.id = 14
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        audit = {"ok": False, "missing_by_protocol": {},
                 "missing_node_memberships": 1,
                 "subscriptions_without_entitlements": 0,
                 "unknown_protocols": []}
        with (patch.object(stage, "SessionLocal") as session,
              # A stable, previously acknowledged Sudoku-only whitelist
              # must not be re-staged for unrelated protocol/membership drift.
              patch.object(stage, "desired_sudoku_fingerprint", return_value="d"*64),
              patch.object(stage, "last_sudoku_applied", return_value="d"*64),
              patch.object(stage, "load_desired_state",
                           return_value=desired_state(3)),
              patch.object(stage, "verify_coverage", return_value=audit)):
            session.return_value.__enter__.return_value = db
            self.assertEqual(stage.missing_runtime_families(14, 3000), ())

    def test_delta_selector_fails_closed_on_unmapped_or_invalid_coverage(self):
        fake = MagicMock()
        fake.id = 14
        fake.retired_at = None
        fake.node_type = NodeType.EXIT
        fake.status = NodeStatus.ONLINE
        fake.show_to_users = False
        db = MagicMock()
        db.get.return_value = fake
        audit = {"ok": False, "missing_by_protocol": {},
                 "subscriptions_without_entitlements": 1,
                 "unknown_protocols": []}
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "load_desired_state",
                           return_value=desired_state(3)),
              patch.object(stage, "verify_coverage", return_value=audit)):
            session.return_value.__enter__.return_value = db
            with self.assertRaisesRegex(RuntimeError,
                                        "AUDIT_NOT_RECONCILABLE"):
                stage.missing_runtime_families(14, 3000)

    def test_published_delta_selects_only_missing_family_on_first_pass(self):
        node = MagicMock()
        node.id = 14
        node.show_to_users = True
        node.retired_at = None
        node.node_type = NodeType.EXIT
        node.status = NodeStatus.ONLINE
        db = MagicMock()
        db.get.return_value = node
        selected = (stage.FAMILIES[5],)
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "allow_central_node", return_value=True),
              patch.object(stage, "is_central_node", return_value=True),
              patch.object(stage, "missing_runtime_families",
                           return_value=selected) as missing,
              patch.object(stage, "_run_locked", return_value=0) as execute):
            session.return_value.__enter__.return_value = db
            self.assertEqual(stage.run(14, 3000, True, delta_only=True), 0)
            missing.assert_called_once_with(14, 3000)
            execute.assert_called_once_with(
                14, 3000, True, families=selected, delta_only=True,
            )

    def test_unregistered_or_hidden_delta_cannot_bypass_initial_checks(self):
        node = MagicMock()
        node.id = 14
        node.show_to_users = False
        node.retired_at = None
        node.node_type = NodeType.EXIT
        node.status = NodeStatus.ONLINE
        db = MagicMock()
        db.get.return_value = node
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "allow_central_node", return_value=True),
              patch.object(stage, "is_central_node", return_value=True),
              patch.object(stage, "_run_locked") as execute):
            session.return_value.__enter__.return_value = db
            with self.assertRaisesRegex(RuntimeError, "REGISTERED_VISIBLE_EXIT"):
                stage.run(14, 3000, True, delta_only=True)
            execute.assert_not_called()

    def test_visible_delta_skips_full_bootstrap_but_audits_coverage(self):
        node = MagicMock()
        node.id = 14
        node.retired_at = None
        node.node_type = NodeType.EXIT
        node.status = NodeStatus.ONLINE
        node.show_to_users = True
        db = MagicMock()
        db.get.return_value = node
        with (patch.object(stage, "SessionLocal") as session,
              patch.object(stage, "allow_central_node", return_value=True),
              patch.object(stage, "is_central_node", return_value=True),
              patch.object(stage, "load_desired_state", return_value=desired_state(3)),
              patch.object(stage, "establish_hidden_memberships", return_value=0),
              patch.object(stage, "verify_coverage",
                           return_value={"ok": True}),
              patch.object(stage, "verify_new_exit_readiness",
                           new_callable=AsyncMock) as listener_check,
              patch.object(stage, "ensure_shared_binary",
                           new_callable=AsyncMock) as bootstrap,
              patch.object(stage, "reconcile_runtime_families",
                           new_callable=AsyncMock) as engine):
            session.return_value.__enter__.return_value = db
            self.assertEqual(stage._run_locked(
                14, 3000, True, families=(), delta_only=True,
            ), 0)
            listener_check.assert_not_awaited()
            bootstrap.assert_not_awaited()
            engine.assert_not_awaited()

    def test_shared_sudoku_adapter_replaces_per_user_units(self):
        self.assertIn("twinpanel_central_sudoku_shared_v2.py",stage.ADAPTERS)
        self.assertNotIn("twinpanel_central_sudoku_node_bulk_v1.py",stage.ADAPTERS)


if __name__ == "__main__":
    unittest.main()
