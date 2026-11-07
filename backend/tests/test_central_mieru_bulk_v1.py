"""Mieru bulk primitive contracts; no live node or secrets required."""
from __future__ import annotations

import unittest
from app.central_mieru_bulk_runtime_v1 import (
    MAX_ACCOUNTS, remote_source, verify_accounts,
)


class MieruCentralBulkTests(unittest.TestCase):
    def test_remote_program_is_syntax_valid(self):
        source = remote_source()
        compile(source, "<central-mieru-bulk-remote>", "exec")
        self.assertIn('["mita","replace","config"', source)
        self.assertIn('["mita","start"]', source)
        self.assertNotIn('for row in incoming:\n        subprocess.run(["mita"', source)

    def test_duplicate_user_blocked(self):
        item = {"username": "tp-sub-123", "password": "safely-long-secret"}
        with self.assertRaisesRegex(ValueError, "INVALID_ACCOUNT"):
            verify_accounts([item, item])

    def test_missing_and_injected_usernames_blocked(self):
        for username in ("", "tp-sub-0", "other", "tp-sub-1\nroot", "tp-sub-1;exit"):
            with self.subTest(username=username):
                with self.assertRaises(ValueError):
                    verify_accounts([{"username":username, "password":"12345678"}])

    def test_bounded_and_valid(self):
        verify_accounts([{"username":"tp-sub-1","password":"password-123"}])
        with self.assertRaisesRegex(ValueError, "INVALID_BATCH_SIZE"):
            verify_accounts([])
        with self.assertRaisesRegex(ValueError, "INVALID_BATCH_SIZE"):
            verify_accounts([{"username":f"tp-sub-{i+1}","password":"password-123"}
                             for i in range(MAX_ACCOUNTS+1)])


if __name__ == "__main__":
    unittest.main()
