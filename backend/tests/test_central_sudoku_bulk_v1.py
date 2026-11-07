"""Sudoku single-session bounded staging contracts."""
from __future__ import annotations

import unittest

from app.central_sudoku_bulk_runtime_v1 import remote_source, verify_accounts
from app.services.central_sudoku_capacity_v1 import sudoku_port


class SudokuCentralBulkTests(unittest.TestCase):
    def row(self, sid):
        return {"subscription_id":sid, "port":sudoku_port(sid),
                "master_public":"a"*64}

    def test_remote_code_compiles_and_waves_are_bounded(self):
        source=remote_source()
        compile(source,"<sudoku-bulk-remote>","exec")
        self.assertIn('["systemctl","start","--no-block",*units]',source)\n        self.assertIn('["systemctl","enable",*units]',source)\n        self.assertIn('["systemctl","list-units","--type=service"',source)\n        self.assertNotIn("systemctl\",\"is-active",source)
        self.assertIn("SUDOKU_TARGET_MEMORY_ADMISSION_FAILED",source)
        self.assertIn("SUDOKU_TARGET_SERVICE_CAPACITY_EXCEEDED",source)
        self.assertIn('["systemctl","daemon-reload"]',source)
        self.assertIn('["systemctl","stop",*units]',source)

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
