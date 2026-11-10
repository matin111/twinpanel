from __future__ import annotations

import ast
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "twinpanel_host_resilience_policy_v1.py"
spec = importlib.util.spec_from_file_location("resilience_v1", SCRIPT)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class HostReliabilityGuard(unittest.TestCase):
    def test_policy_is_safe_scope_and_has_hard_disk_limit(self):
        ast.parse(SCRIPT.read_text())
        self.assertEqual(policy.DB_NAME, "twinpanel")
        self.assertEqual(policy.DB_IDLE_LIMIT, "180s")
        self.assertIn("SystemMaxUse=2G", policy.JOURNAL_TEXT)
        self.assertIn("SystemKeepFree=3G", policy.JOURNAL_TEXT)
        self.assertIn("MaxRetentionSec=14day", policy.JOURNAL_TEXT)

    def test_readonly_audit_never_mutates_live_host(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(policy, "JOURNAL_DROPIN", Path(d)/"policy.conf"), \
                mock.patch.object(policy, "db_config", return_value="idle_in_transaction_session_timeout=180s"), \
                mock.patch.object(policy, "run", side_effect=AssertionError("unexpected command")):
            status = policy.inspect()
            self.assertFalse(status["journal_policy_installed"])
            self.assertTrue(status["postgres_idle_guard_enabled"])

    def test_mutation_requires_root(self):
        with mock.patch.object(policy.os, "geteuid", return_value=1000), \
                mock.patch.object(policy, "run", side_effect=AssertionError("unexpected command")):
            with self.assertRaisesRegex(RuntimeError, "ROOT_REQUIRED"):
                policy.apply()

    def test_apply_never_restarts_database_or_mutates_user_subscriptions(self):
        source = SCRIPT.read_text()
        self.assertNotIn("systemctl restart", source)
        self.assertNotIn("DROP DATABASE", source)
        self.assertNotIn("ALTER ROLE", source)
        self.assertNotIn("quota_sessions", source)
        self.assertIn('ALTER DATABASE {DB_NAME}', source)
        self.assertIn('if journal_cleanup:', source)

    def test_probe_fails_when_database_flag_missing(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(policy, "JOURNAL_DROPIN", Path(d)/"policy.conf"), \
                mock.patch.object(policy, "db_config", return_value=""):
            status = policy.inspect()
            self.assertFalse(status["postgres_idle_guard_enabled"])


if __name__ == "__main__":
    unittest.main()
