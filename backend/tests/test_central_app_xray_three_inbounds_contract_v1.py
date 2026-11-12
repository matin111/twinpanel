"""Regression guard for TwinConnect Xray three-inbound delivery contract.

This intentionally checks the controller API; native Windows engine availability
must be verified separately in the desktop application's own repository.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "backend/app/routers/central_app_v1.py"
FEED = ROOT / "backend/app/routers/public_connection_multilink_v7.py"
CATALOG = ROOT / "backend/app/central_app_protocols.py"


class CentralAppXrayThreeInboundsContract(unittest.TestCase):
    def test_controller_sources_parse(self):
        for file in (API, FEED, CATALOG):
            with self.subTest(file=file.name):
                ast.parse(file.read_text(encoding="utf-8"))

    def test_app_returns_canonical_live_server_groups_without_breaking_items(self):
        source = API.read_text(encoding="utf-8")
        self.assertIn("_v2ray_profile_groups(", source)
        self.assertIn('"server_groups": jsonable_encoder(server_groups)', source)
        self.assertIn('"items": jsonable_encoder(profile_items)', source)
        self.assertIn('"native_engine_ready": False', source)
        self.assertIn('protocol == "v2ray"', source)

    def test_canonical_feed_preserves_three_independent_profiles(self):
        feed = FEED.read_text(encoding="utf-8")
        self.assertIn("def _v2ray_profile_groups(", feed)
        self.assertIn("def _apply_live_xray_uri(", feed)
        self.assertIn('"profile_count": len(profile_rows)', feed)
        self.assertIn('"profiles": profile_rows', feed)
        self.assertIn("if not uris:", feed)
        catalog = CATALOG.read_text(encoding="utf-8")
        self.assertIn("Preserve TCP TLS, XHTTP Reality and WS TLS individually.", catalog)


if __name__ == "__main__":
    unittest.main()
