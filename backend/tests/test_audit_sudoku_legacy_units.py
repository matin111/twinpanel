"""Read-only legacy Sudoku unit inventory: isolated regression tests."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_sudoku_legacy_units import audit


class SudokuLegacyAuditTests(unittest.TestCase):
    def test_no_legacy_artifacts_is_clean(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            self.assertEqual(audit(path / "units", path / "subscriptions",
                                   probe_systemd=False)["legacy_count"], 0)

    def test_owned_units_only_and_orphan_config_detected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            units, subs = path / "units", path / "subscriptions"
            units.mkdir()
            subs.mkdir()
            (units / "twinpanel-sudoku-sub-3900.service").write_text("[Unit]\n")
            (units / "twinpanel-sudoku.service").write_text("[Unit]\n")
            (units / "foreign-sudoku-sub-4040.service").write_text("[Unit]\n")
            (subs / "3902").mkdir()
            report = audit(units, subs, probe_systemd=False)
            self.assertEqual(report["legacy_units"], 1)
            self.assertEqual(report["legacy_config_directories"], 1)
            self.assertEqual([x["subscription_id"] for x in report["entries"]],
                             [3900, 3902])
            self.assertFalse(report["entries"][0]["config_directory_present"])
            self.assertFalse(report["entries"][1]["unit_present"])

    def test_never_reads_customer_config_or_runs_systemctl_when_disabled(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            units, subs = path / "units", path / "subscriptions"
            units.mkdir()
            subs.mkdir()
            unit = units / "twinpanel-sudoku-sub-3903.service"
            unit.write_text("CUSTOMER_SECRET_MUST_NOT_APPEAR")
            (subs / "3903").mkdir()
            with patch("subprocess.run") as subprocess_mock:
                result = audit(units, subs, probe_systemd=False)
                subprocess_mock.assert_not_called()
            self.assertNotIn("CUSTOMER_SECRET", str(result))
            self.assertEqual(unit.read_text(), "CUSTOMER_SECRET_MUST_NOT_APPEAR")


if __name__ == "__main__":
    unittest.main()
