"""Sudoku single-session bounded staging contracts."""
from __future__ import annotations

import unittest

from app.central_sudoku_bulk_runtime_v1 import remote_source, verify_accounts
from app.services.central_sudoku_capacity_v1 import sudoku_port


class SudokuCentralBulkTests(unittest.TestCase):
    def row(self, sid):
        return {"subscription_id":sid, "port":sudoku_port(sid),
                "master_public":"a"*64}

    def test_obsolete_remote_installer_fails_closed(self):
        # The old per-user systemd writer must not be embedded in source.
        with self.assertRaisesRegex(RuntimeError, "SUDOKU_LEGACY_BULK_DISABLED"):
            remote_source()
        with self.assertRaisesRegex(RuntimeError, "SUDOKU_LEGACY_BULK_DISABLED"):
            remote_source(base="/tmp/test", unit_dir="/tmp/units")

    def test_retired_module_has_no_installer_commands(self):
        from pathlib import Path
        import app.central_sudoku_bulk_runtime_v1 as legacy
        source = Path(legacy.__file__).read_text(encoding="utf-8")
        self.assertNotIn("systemctl", source)
        self.assertNotIn("create_process(", source)
        self.assertNotIn("unit.write_text(", source)
        self.assertNotIn("BASE.mkdir(", source)

    def test_capacity_limit_and_collision(self):
        verify_accounts([self.row(1),self.row(2)])
        verify_accounts([self.row(x) for x in range(1,1901)])
        with self.assertRaisesRegex(ValueError,"CAPACITY"):
            verify_accounts([self.row(x) for x in range(1,3002)])
        with self.assertRaisesRegex(ValueError,"INVALID_PORT"):
            verify_accounts([self.row(1),self.row(30001)])

    def test_rejects_suspicious_public_key_and_port_override(self):
        for candidate in [
            {**self.row(1),"master_public":"unsafe"},
            {**self.row(1),"port":443},
            {**self.row(1),"master_public":"x"*64},
        ]:
            with self.assertRaises(ValueError):
                verify_accounts([candidate])


if __name__=="__main__":
    unittest.main()
