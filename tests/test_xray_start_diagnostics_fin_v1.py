"""Regression guard: Xray start failure reports safe diagnostics before rollback."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / "backend" / "app" / "xray_modern_runtime.py")


class XrayStartDiagnosticsTest(unittest.TestCase):
    def test_failure_diagnostics_precede_rollback(self):
        text = SOURCE.read_text(encoding="utf-8")
        diagnostic = text.index("systemctl show xray.service")
        restore = text.index("rollback_result =")
        failure = text.index('"XRAY_MODERN_START_VERIFICATION_FAILED "')
        self.assertLess(diagnostic, restore)
        self.assertLess(restore, failure)

    def test_no_credential_bearing_journal_in_error(self):
        text = SOURCE.read_text(encoding="utf-8")
        start = text.index('diagnostics = "unavailable"')
        end = text.index('raise RuntimeError(\n            "XRAY_MODERN_START_VERIFICATION_FAILED', start)
        block = text[start:end]
        self.assertIn("-p ExecMainStatus", block)
        self.assertNotIn("journalctl", block)
        self.assertIn("missing_listeners", text)
        self.assertIn('rollback_result = "failed"', block)


if __name__ == "__main__":
    unittest.main()
