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
