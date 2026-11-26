"""Guardrail tests for opt-in migration of previously published Sudoku Exits.

No network, runtime services, subscriptions or credentials are mutated here.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

BACKEND=Path(__file__).resolve().parents[1]
STAGE=BACKEND/"scripts/twinpanel_central_sudoku_shared_v2.py"
MARKER=BACKEND/"app/services/legacy_sudoku_shared_migration_v1.py"
WORKER=BACKEND/"scripts/twinpanel_sudoku_fast_presence_worker.py"
DELIVERY=BACKEND/"app/services/sudoku_central_delivery_v1.py"
SCHEDULER=BACKEND/"app/services/central_runtime_visible_convergence_v1.py"
ENFORCE=BACKEND/"app/services/sudoku_central_enforcement_v1.py"


class PublishedLegacySudokuMigrationTests(unittest.TestCase):
    def test_all_modified_sources_compile(self):
        for path in (STAGE,MARKER,WORKER,DELIVERY,SCHEDULER,ENFORCE):
            with self.subTest(path=path.name):
                compile(path.read_text(),str(path),"exec")

    def test_only_explicit_scoped_migration_can_write_to_published_legacy_exit(self):
        source=STAGE.read_text()
        self.assertIn("migrate_legacy and node is not None",source)
        self.assertIn("not is_central_node(db,int(node_id))",source)
        self.assertIn("migrate_legacy and not migrated_candidate",source)
        self.assertIn("if opt.migrate_legacy and (not opt.apply or opt.confirm_node_id!=opt.node_id)",source)
        self.assertIn("SUDOKU_SHARED_LEGACY_MIGRATION_SCOPE_INVALID",source)

    def test_mark_shared_only_after_authenticated_apply_and_subscription_save(self):
        tree=ast.parse(STAGE.read_text())
        stages=[node for node in tree.body if isinstance(node,ast.AsyncFunctionDef)
                and node.name=="stage"]
        self.assertEqual(len(stages),1)
        source=ast.get_source_segment(STAGE.read_text(),stages[0])
        self.assertLess(source.index("ack=await apply"),source.index("mark_legacy_shared_node(db,node_id)"))
        self.assertLess(source.index("cred.config_text_encrypted=ad._enc(next_items)"),
                        source.index("mark_legacy_shared_node(db,node_id)"))
        self.assertNotIn("mark_central_node(",source)

    def test_delivery_metering_revoke_and_expiry_have_scoped_ownership(self):
        self.assertIn("is_legacy_shared_node(db,node_id)",DELIVERY.read_text())
        self.assertIn("is_legacy_shared_node(db,node_id)",SCHEDULER.read_text())
        self.assertIn("launch_legacy_shared_reconcile",SCHEDULER.read_text())
        self.assertIn("or is_legacy_shared_node(db, node_id)",WORKER.read_text())
        self.assertIn("launch_legacy_shared_reconcile",ENFORCE.read_text())
        self.assertIn("source_protocols={\"sudoku\"}",WORKER.read_text())
        self.assertIn('if int(unit["sid"]) in counters',WORKER.read_text())

    def test_german_shared_ingress_is_unique_to_tunnel_40(self):
        from app.services.legacy_sudoku_shared_migration_v1 import public_shared_sudoku_port
        self.assertEqual(public_shared_sudoku_port(6),18553)
        self.assertEqual(public_shared_sudoku_port(13),18554)
        self.assertEqual(public_shared_sudoku_port(11),18553)
        source=STAGE.read_text()
        self.assertIn("public_port=public_shared_sudoku_port(int(node.id))",source)
        self.assertIn("_sudoku_endpoint(host,public_port)",source)
        self.assertIn('"port":public_port',source)
        self.assertIn("port != public_shared_sudoku_port(node_id)",DELIVERY.read_text())

    def test_launcher_uses_fixed_node_unit_and_global_lock(self):
        source=MARKER.read_text()
        self.assertIn("twinpanel-legacy-sudoku-shared-{nid}",source)
        self.assertIn("/tmp/twinpanel-central-node-stage-global.lock",source)
        self.assertIn('"--migrate-legacy"',source)
        self.assertIn("not is_legacy_shared_node(db, nid)",source)


if __name__=="__main__":
    unittest.main()
