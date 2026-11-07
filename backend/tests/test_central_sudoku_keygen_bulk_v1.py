"""Safety checks for single-SSH Sudoku bulk key generation."""
from __future__ import annotations

import unittest

from app.central_sudoku_keygen_bulk_v1 import (
    MAX_KEYS, remote_source, validate_ids,
)


class SudokuKeygenBulkTests(unittest.TestCase):
    def test_remote_program_compiles_and_runs_parallel_locally(self):
        program=remote_source()
        compile(program,"<sudoku-keygen-remote>","exec")
        self.assertIn("ThreadPoolExecutor(max_workers=16)",program)
        self.assertIn('BINARY),"-keygen"',program)
        self.assertNotIn("shell=True",program)

    def test_1900_distinct_ids_are_allowed(self):
        validate_ids(list(range(1,1901)))

    def test_duplicate_or_unbounded_ids_are_rejected(self):
        for ids in ([],[1,1],[0],[1,"2"],list(range(1,MAX_KEYS+2))):
            with self.subTest(length=len(ids)):
                with self.assertRaises(ValueError):
                    validate_ids(ids)


if __name__ == "__main__":
    unittest.main()
