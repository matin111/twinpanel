"""Guard legacy backfill CPU preflight before importing the full application."""
from __future__ import annotations

import ast
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/twinpanel_node_auto_backfill_v1.py"


class NodeAutoBackfillPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=SCRIPT.read_text(encoding="utf-8")
        cls.source=source
        module=ast.parse(source)
        function=next(
            node for node in module.body
            if isinstance(node,ast.FunctionDef) and node.name=="_cheap_priority_guard"
        )
        namespace={"os":Mock(),"subprocess":subprocess}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(SCRIPT),"exec"),namespace)
        cls.guard=staticmethod(namespace["_cheap_priority_guard"])

    def test_preflight_runs_before_application_imports(self):
        self.assertLess(self.source.index("if __name__ == \"__main__\" and _cheap_priority_guard()"),
                        self.source.index("from app.database import SessionLocal"))
        self.assertIn("NODE_AUTO_BACKFILL_FAST_PRIORITY_PAUSED",self.source)

    def test_busy_controller_skips_before_systemd_process_scan(self):
        with patch("os.getloadavg",return_value=(8.2,6,5)), \
             patch("subprocess.run") as run:
            self.assertTrue(self.guard())
            run.assert_not_called()

    def test_running_central_stage_skips_heavy_backfill(self):
        result=SimpleNamespace(
            returncode=0,
            stdout="twinpanel-central-node-stage-29.service loaded active running sample\n",
        )
        with patch("os.getloadavg",return_value=(3,3,3)), \
             patch("subprocess.run",return_value=result):
            self.assertTrue(self.guard())

    def test_idle_node_fleet_keeps_original_full_guard(self):
        result=SimpleNamespace(returncode=0,stdout="")
        with patch("os.getloadavg",return_value=(3,3,3)), \
             patch("subprocess.run",return_value=result):
            self.assertFalse(self.guard())


if __name__=="__main__":
    unittest.main()
