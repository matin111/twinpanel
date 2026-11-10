"""Only clean, opted-in V314 database reads may end before CPU-heavy mapping."""
from __future__ import annotations

import inspect
import unittest

from app.services import accounting_device_map_batch_v1 as batch
from app.services import modern_quota_runtime_v314 as runtime


class FakeSession:
    def __init__(self, active, *, staged=False):
        self.info = {batch._CLEAN_READ_LOOKUP_FLAG: active}
        self.new = {1} if staged else set()
        self.dirty = set()
        self.deleted = set()
        self.commits = 0

    def commit(self):
        self.commits += 1


class BulkReadBoundarySmoke(unittest.TestCase):
    def test_clean_worker_read_can_commit(self):
        db = FakeSession(True)
        batch._release_bulk_read_if_safe(db)
        self.assertEqual(db.commits, 1)

    def test_unflagged_callers_preserve_transaction(self):
        db = FakeSession(False)
        batch._release_bulk_read_if_safe(db)
        self.assertEqual(db.commits, 0)

    def test_pending_writes_are_never_committed_implicitly(self):
        db = FakeSession(True, staged=True)
        batch._release_bulk_read_if_safe(db)
        self.assertEqual(db.commits, 0)

    def test_all_large_cpu_sections_follow_read_boundary(self):
        src = inspect.getsource(batch.build_accounting_devices_by_node)
        self.assertLess(src.index("_release_bulk_read_if_safe(db)"),
                        src.index("decoded_by_credential"))
        self.assertLess(src.index("_release_bulk_read_if_safe(db)", src.index("legacy_nodes_by_subscription")),
                        src.index("for subscription_id, node_id in rows:"))
        self.assertLess(src.index("_release_bulk_read_if_safe(db)", src.index("devices = (")),
                        src.index("for device in devices:"))
        self.assertIn('db.info["twinpanel_v314_clean_lookup_session"] = True',
                      inspect.getsource(runtime.reconcile_modern_quota_once))


if __name__ == "__main__":
    unittest.main()
