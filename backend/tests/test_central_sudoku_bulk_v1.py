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
        self.assertIn("range(0,len(newly_created),4)",source)
        self.assertIn('["systemctl","daemon-reload"]',source)
        self.assertIn('["systemctl","disable","--now",name]',source)

    def test_capacity_limit_and_collision(self):
        verify_accounts([self.row(1),self.row(2)])
        with self.assertRaisesRegex(ValueError,"CAPACITY"):
            verify_accounts([self.row(x) for x in range(1,66)])
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
