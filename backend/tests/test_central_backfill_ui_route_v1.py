"""Central Exits must never retry the legacy subscriber backfill queue."""
from pathlib import Path
import ast
import unittest

ROOT=Path(__file__).resolve().parents[2]
ROUTES=ROOT/"backend/app/routers/publish_node_all_users_v2.py"
UI=ROOT/"components/legacy-nodes-runtime-v2.tsx"


class CentralBackfillRouteTests(unittest.TestCase):
    def test_legacy_retry_goes_to_central_launcher(self):
        source=ROUTES.read_text(encoding="utf8")
        ast.parse(source)
        retry=source.split('def retry_node_backfill_v1(',1)[1].split(
            '# The detached installer',1)[0]
        self.assertIn('if is_central_node(db, int(node_id)):',retry)
        self.assertIn('started = launch(db, int(node_id))',retry)
        self.assertLess(retry.index('started = launch(db, int(node_id))'),
                        retry.index('enqueue_node_backfill(db, node_id'))
        self.assertIn('result["central_runtime"] = True',retry)

    def test_ui_uses_central_endpoint_and_central_state(self):
        source=UI.read_text(encoding="utf8")
        self.assertIn('backfill?.central_runtime?"central-stage":"backfill-retry"',source)
        self.assertIn('backfill?.central_runtime?pick("مدیریت مرکزی"',source)
        self.assertIn('backfill?.central_runtime?pick("شروع همگام‌سازی مرکزی"',source)


if __name__=="__main__":
    unittest.main()
