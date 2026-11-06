"""Regression: keep VLESS inbound TCP policy unchanged after BBR canary rollback."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ROOT / "backend" / "app" / "xray_modern_runtime.py",
    ROOT / "backend" / "app" / "xray_tcp_tls_v39.py",
]


class XrayBbrRollbackTest(unittest.TestCase):
    def test_no_forced_tcp_congestion_in_customer_inbound_generators(self):
        for path in SOURCES:
            contents = path.read_text(encoding="utf-8")
            self.assertNotIn('"tcpCongestion": "bbr"', contents, path.name)
            self.assertNotIn('tcp_congestion_control', contents, path.name)

    def test_no_bulk_bbr_applier_left_in_release(self):
        self.assertFalse(
            (ROOT / "backend" / "scripts" / "xray_vless_inbound_bbr_v1.py").exists()
        )


if __name__ == "__main__":
    unittest.main()
