"""Guard the safe, real-byte Sudoku shared accounting path in release builds.

No database, network, or third-party imports.
"""
from pathlib import Path
import ast
import unittest

ROOT=Path(__file__).resolve().parents[1]

class SudokuSharedAccountingReleaseTests(unittest.TestCase):
    def test_controller_collects_and_validates_real_counters(self):
        source=(ROOT/"app/services/sudoku_shared_native_presence_v1.py").read_text()
        ast.parse(source)
        self.assertIn('upTotal',source)
        self.assertIn('downTotal',source)
        self.assertIn('"InvocationID"',source)
        self.assertIn('used!=up+down',source)
        self.assertIn('validated_counters',source)

    def test_accounting_uses_epoch_baseline_and_exact_user_identity(self):
        source=(ROOT/"app/services/sudoku_shared_native_presence_v1.py").read_text()
        self.assertIn('def apply_shared_native_counters(',source)
        self.assertIn('source_key=f"sudoku:shared:{sid}:{epoch}"',source)
        self.assertIn('canonical._baseline_or_apply_cumulative(',source)
        self.assertIn('if sid in seen:',source)

    def test_worker_uses_native_verified_counters_not_estimated_speed(self):
        source=(ROOT/"scripts/twinpanel_sudoku_fast_presence_worker.py").read_text()
        ast.parse(source)
        self.assertIn('usage=apply_shared_native_counters(',source)
        self.assertIn('apply_legacy_unit_counters(',source)
        self.assertIn('apply_shared_native_presence(',source)

if __name__=="__main__":unittest.main()
