"""Core Xray provisioning must never override a dedicated TLS hostname."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

from app.xray_modern_runtime import _preferred_node_xray_domain


class XrayCoreDomainPrecedenceTests(TestCase):
    def test_dedicated_domain_wins_over_shared_node_domain(self):
        node = SimpleNamespace(
            id=11, xray_domain="v2usa.in88.sbs",
            public_domain="tunel.in88.sbs",
        )
        self.assertEqual(
            _preferred_node_xray_domain(node), "v2usa.in88.sbs",
        )

    def test_finland_dedicated_domain_wins(self):
        node = SimpleNamespace(
            id=22, xray_domain="v2fin.in88.sbs",
            public_domain="fin.in88.sbs",
        )
        self.assertEqual(
            _preferred_node_xray_domain(node), "v2fin.in88.sbs",
        )

    def test_legacy_node_falls_back_without_dedicated_domain(self):
        node = SimpleNamespace(public_domain="legacy.example.com")
        self.assertEqual(
            _preferred_node_xray_domain(node), "legacy.example.com",
        )
        self.assertEqual(_preferred_node_xray_domain(None), "")

    def test_base_provisioner_uses_core_domain_precedence_not_public_domain(self):
        source=(
            Path(__file__).resolve().parents[1]
            / "app/xray_modern_runtime.py"
        ).read_text()
        ensure=source.split("async def _ensure_modern_xray(",1)[1]
        self.assertIn("domain = _preferred_node_xray_domain(node)",ensure)
        self.assertNotIn(
            '_clean_domain(getattr(node, "public_domain", None))',
            ensure.split("state_script = _state_generator_script(domain)",1)[0],
        )


if __name__ == "__main__":
    import unittest
    unittest.main()
