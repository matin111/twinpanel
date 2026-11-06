from __future__ import annotations

import ast
import unittest
from pathlib import Path


UPDATER = Path(__file__).resolve().parents[1] / "backend" / "scripts" / "twinpanel_public_updater.py"


class ReleaseBoundHeavyWorkerTest(unittest.TestCase):
    def test_updater_restarts_release_bound_worker_after_switch(self):
        tree = ast.parse(UPDATER.read_text(encoding="utf-8"))
        methods = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertTrue({"existing_units", "restart_services", "rollback"}.issubset(methods))

        existing = ast.get_source_segment(
            UPDATER.read_text(encoding="utf-8"), methods["existing_units"]
        )
        self.assertIn("'twinpanel-heavy-reconcile.service'", existing)
        self.assertIn("'twinpanel-api.service'", existing)
        self.assertIn("'twinpanel-web.service'", existing)

        restart = ast.get_source_segment(
            UPDATER.read_text(encoding="utf-8"), methods["restart_services"]
        )
        self.assertIn("'--no-block'", restart)
        self.assertIn("'restart'", restart)
        self.assertIn("existing_units()", restart)

        rollback = ast.get_source_segment(
            UPDATER.read_text(encoding="utf-8"), methods["rollback"]
        )
        self.assertIn("restart_services()", rollback)


if __name__ == "__main__":
    unittest.main()
