"""Independent presence pollers may end clean credential SELECTs before CPU mapping.

No user/node/session mutation. SQLAlchemy sessions containing pending writes
are never committed by the shared helper.
"""
from __future__ import annotations
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY = "twinpanel_v314_clean_lookup_session"


class CleanPresenceReadBoundary(unittest.TestCase):
    def test_presence_only_fresh_sessions_opt_in_before_node_reads(self):
        for name in (
            "twinpanel_naive_fast_presence_worker.py",
            "twinpanel_sudoku_fast_presence_worker.py",
        ):
            with self.subTest(name=name):
                source = (ROOT / "scripts" / name).read_text()
                ast.parse(source)
                self.assertIn(f'db.info["{KEY}"] = True', source)
                self.assertLess(source.index("    db = SessionLocal()"),
                                source.index(f'db.info["{KEY}"] = True'))
                self.assertLess(source.index(f'db.info["{KEY}"] = True'),
                                source.index("db.query(Node"))
                self.assertIn("close_read_transaction_before_ssh=True", source)
                self.assertIn("db.rollback()", source)

    def test_presence_workers_select_only_source_protocol_credentials(self):
        from app.services import accounting_device_map_batch_v1 as batch
        import inspect
        source=inspect.getsource(batch.build_accounting_devices_by_node)
        self.assertIn("ProtocolCredential.protocol.in_(sorted(selected))",source)
        self.assertLess(source.index("ProtocolCredential.protocol.in_(sorted(selected))"),
                        source.index("decoded_by_credential"))
        self.assertIn("source_protocols=source_protocols",
                      inspect.getsource(batch.build_presence_devices_for_protocols))
        workers={
            "twinpanel_naive_fast_presence_worker.py":
                'source_protocols={"naive", "naiveproxy"}',
            "twinpanel_sudoku_fast_presence_worker.py":
                'source_protocols={"sudoku"}',
        }
        for name,needle in workers.items():
            with self.subTest(name=name):
                text=(ROOT/"scripts"/name).read_text()
                self.assertIn("build_presence_devices_for_protocols(",text)
                self.assertIn(needle,text)
                self.assertIn("close_read_transaction_before_ssh=True",text)

    def test_full_accounting_mapping_still_unfiltered_by_default(self):
        import inspect
        from app.services import accounting_device_map_batch_v1 as batch
        self.assertIsNone(inspect.signature(batch.build_accounting_devices_by_node)
                          .parameters["source_protocols"].default)
        self.assertIn("build_accounting_devices_by_node(db)",
                      inspect.getsource(batch.build_node_devices_cached))

    def test_scoped_builder_executes_database_protocol_filter(self):
        from unittest.mock import MagicMock,patch
        from app.services import accounting_device_map_batch_v1 as batch
        db=MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value=[]
        with (patch.object(batch,"_candidate_node_ids",return_value=[19]),
              patch.object(batch,"is_openvpn_central_pki_enabled",return_value=False)):
            actual=batch.build_presence_devices_for_protocols(
                db,source_protocols={"sudoku"})
        self.assertEqual(actual,{19:[]})
        filter_expressions=[
            str(call.args[0]) for call in
            db.query.return_value.filter.call_args_list
        ]
        self.assertTrue(any("protocol_credentials.protocol IN" in x
                            for x in filter_expressions))
        self.assertTrue(any("protocol_credentials.is_active" in x
                            for x in filter_expressions))

    def test_scoped_builder_rejects_invalid_or_empty_source_protocol(self):
        from unittest.mock import MagicMock,patch
        from app.services import accounting_device_map_batch_v1 as batch
        with patch.object(batch,"_candidate_node_ids",return_value=[19]):
            for source in (set(),{"not-real-protocol"}):
                with self.assertRaisesRegex(ValueError,"ACCOUNTING_SOURCE_PROTOCOL_SCOPE_INVALID"):
                    batch.build_presence_devices_for_protocols(
                        MagicMock(),source_protocols=source)

    def test_guarded_shared_read_helper_preserves_pending_mutations(self):
        from app.services import accounting_device_map_batch_v1 as batch
        class Fake:
            def __init__(self, dirty=False):
                self.info = {KEY: True}
                self.new = set()
                self.deleted = set()
                self.dirty = {1} if dirty else set()
                self.commits = 0
            def commit(self):
                self.commits += 1
        active, dirty = Fake(), Fake(dirty=True)
        batch._release_bulk_read_if_safe(active)
        batch._release_bulk_read_if_safe(dirty)
        self.assertEqual(active.commits, 1)
        self.assertEqual(dirty.commits, 0)


if __name__ == "__main__":
    unittest.main()
