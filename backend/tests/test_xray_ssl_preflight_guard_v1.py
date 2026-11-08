"""Regression guard for bounded Xray SSL preparation.

This is a source-contract test, so it does not contact or alter VPN nodes.
"""
from pathlib import Path
import ast
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "app" / "xray_modern_admin.py"
ADMIN_API = Path(__file__).resolve().parents[2] / "lib" / "admin-api.ts"


class XraySslPreflightTests(unittest.TestCase):
    def test_acme_check_before_install_and_firewall(self):
        source = SOURCE.read_text(encoding="utf-8")
        ast.parse(source)
        section = source.split("async def _issue_certificate(", 1)[1].split("async def _status_remote(", 1)[0]
        self.assertIn("xray_tls_acme_unreachable", section)
        self.assertLess(section.index("acme_reachable ="), section.index("apt-get"))
        self.assertLess(section.index("acme_reachable ="), section.index("provision.ufw_allow"))
        self.assertIn("--connect-timeout 5 --max-time 9", section)
        self.assertNotIn("timeout=600", section)
        self.assertNotIn("systemctl restart", section)
        self.assertNotIn("systemctl stop", section)

    def test_structured_error_is_visible_to_admin(self):
        source = ADMIN_API.read_text(encoding="utf-8")
        self.assertIn('if(typeof detail.message==="string")return detail.message;', source)


if __name__ == "__main__":
    unittest.main()
