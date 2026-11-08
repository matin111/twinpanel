"""Regression guard: stale TLS state must not hide verified Reality Exits."""
import ast
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "app/central_xray_node_authority_v1.py"


class VerifiedAuthorityFallbackTests(unittest.TestCase):
    def test_tls_requires_both_installed_tls_profiles(self):
        source=SOURCE.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn('"vless-ws-tls" in inbounds',source)
        self.assertIn('"vless-tcp-tls" in inbounds',source)
        self.assertIn('tls_enabled=(bool(state.get("tls_enabled"))',source)

    def test_reality_fallback_still_validates_security_and_live_vision(self):
        source=SOURCE.read_text(encoding="utf-8")
        self.assertIn('xhttp=must("vless-xhttp-reality","xhttp","reality")',source)
        self.assertIn('tcp=must("vless-tcp-reality","tcp","reality")',source)
        self.assertIn('vision=must("vless-tcp-reality-vision","tcp","reality")',source)
        self.assertIn('XRAY_NODE_VISION_REALITY_MISMATCH',source)
        self.assertIn('if running and listener.returncode==0',source)


if __name__=="__main__":
    unittest.main()
