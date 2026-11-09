"""All retired Sudoku V1 CLI paths fail before network, DB or key generation."""
from __future__ import annotations

import asyncio
import inspect
import unittest
from pathlib import Path

from scripts import twinpanel_central_sudoku_node_bulk_v1 as stage_module


class SudokuStageTests(unittest.TestCase):
    def test_cli_accepts_legacy_arguments_only_for_explicit_rejection(self):
        args = stage_module.args(["--node-id", "14", "--limit", "3000",
                                  "--apply", "--confirm-node-id", "14"])
        self.assertEqual(args.node_id, 14)
        self.assertTrue(args.apply)

    def test_stage_fails_closed_for_apply_and_dry_run(self):
        for apply in (False, True):
            with self.assertRaisesRegex(RuntimeError,
                                         "SUDOKU_LEGACY_STAGE_RETIRED_USE_SHARED_V2"):
                asyncio.run(stage_module.stage(14, 3000, apply))

    def test_no_legacy_staging_imports_or_writers_remain(self):
        source = Path(inspect.getfile(stage_module)).read_text(encoding="utf-8")
        for legacy in ("SessionLocal", "generate_many", "connect_protocol_runtime",
                       "db.commit(", "with_for_update(", "apply_bulk(",
                       "StandaloneAccountSecret", "systemctl"):
            self.assertNotIn(legacy, source)

    def test_legacy_client_item_no_longer_published(self):
        self.assertFalse(hasattr(stage_module, "client_item"))


if __name__ == "__main__":
    unittest.main()
