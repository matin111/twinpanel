"""Do not ship HTML masquerading as APKs or OS-mismatched client links.

No customer/production database or network calls are needed to run these.
The audited assets were independently HEAD-checked before being pinned.
"""
from __future__ import annotations

from pathlib import Path
import unittest

from app.routers.public_connection_client_catalog_v821 import (
    APPS, ALTERNATIVE_ASSETS, PLATFORMS, PROTOCOL_CLIENT, app_for_protocol,
    client_for, global_downloads, protocol_client_rows,
)
from app.routers.public_connection_app_download_v34 import (
    public_connect_app_download_v34,
)


class AuditedProtocolClientTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1] / "app/routers"

    def test_all_16_protocols_have_correct_device_targets(self):
        expected = {
            "cisco", "openvpn", "wireguard", "l2tp", "v2ray",
            "hysteria2", "tuic", "anytls", "naive", "shadowtls",
            "snell", "mieru", "socks5", "trusttunnel", "amneziawg",
            "sudoku",
        }
        self.assertEqual(set(PROTOCOL_CLIENT), expected)
        self.assertEqual(PROTOCOL_CLIENT["l2tp"], {})
        for proto in expected - {"l2tp"}:
            for platform in PLATFORMS:
                with self.subTest(proto=proto, platform=platform):
                    app = app_for_protocol(proto, platform)
                    self.assertIsNotNone(app)
                    self.assertIn(platform, APPS[app])
                    name, url = APPS[app][platform]
                    self.assertTrue(name)
                    self.assertTrue(url.startswith("https://"))
                    self.assertNotIn("/releases/latest", url)
                    self.assertNotIn("/downloads/apps/", url)
                    self.assertNotIn(".ipa", url)
        self.assertEqual(app_for_protocol("xray", "android"), "v2rayng")
        self.assertEqual(app_for_protocol("v2ray", "ios"), "v2box")
        self.assertEqual(app_for_protocol("cisco", "windows"), "openconnect")
        self.assertEqual(app_for_protocol("naiveproxy", "windows"), "singbox")
        self.assertEqual(app_for_protocol("v2ray", "windows"), "v2rayn")

    def test_real_redirect_is_same_as_catalog_asset(self):
        for app, mappings in APPS.items():
            for platform, (name, url) in mappings.items():
                with self.subTest(app=app, platform=platform):
                    response = public_connect_app_download_v34(app, platform)
                    self.assertEqual(response.status_code, 307)
                    self.assertEqual(response.headers["location"], url)

    def test_public_client_cards_use_direct_redirects(self):
        rows = protocol_client_rows()
        for protocol, apps in rows.items():
            for platform, (name, url) in apps.items():
                self.assertTrue(name)
                self.assertEqual(
                    url,
                    f"/v1/connect/app-download/{PROTOCOL_CLIENT[protocol][platform]}/{platform}",
                )

    def test_global_apps_have_only_verified_entries(self):
        cards = global_downloads()
        self.assertEqual(set(cards), set(PLATFORMS))
        for platform, entries in cards.items():
            self.assertTrue(entries)
            urls = [item["url"] for item in entries]
            self.assertEqual(len(urls), len(set(urls)))
            for item in entries:
                self.assertTrue(item["name"])
                self.assertTrue(item["note"])
                self.assertTrue(item["url"].startswith((
                    "/v1/connect/app-download/", "https://github.com/",
                )))
                self.assertNotIn("/downloads/apps/", item["url"])
        self.assertEqual(len(ALTERNATIVE_ASSETS["macos"]), 2)
        self.assertFalse(any("L2TP" in x["name"] for x in cards["ios"]))

    def test_unverified_assets_cannot_be_returned(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            public_connect_app_download_v34("v2rayng", "windows")
        self.assertEqual(ctx.exception.status_code, 404)
        with self.assertRaises(HTTPException) as ctx:
            public_connect_app_download_v34("l2tp", "android")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_legacy_renderers_do_not_restore_broken_downloads(self):
        modern = (self.root / "public_connection_modern_delivery_v13.py").read_text()
        android = (self.root / "public_connection_canonical_presentation_v24.py").read_text()
        v2ray = (self.root / "public_connection_v2ray_actions_v41.py").read_text()
        footer = (self.root / "public_connection_unified_surface_dates_v80.py").read_text()
        account = (self.root / "account_delivery.py").read_text()
        self.assertIn("CLIENTS: dict[str, dict[str, tuple[str, str]]] = protocol_client_rows()", modern)
        self.assertNotIn("const DIRECT_APPS", android)
        self.assertNotIn("Hiddify-iOS.ipa", android)
        self.assertIn('protocol_client_rows()["v2ray"]', v2ray)
        self.assertNotIn("https://github.com/2dust/v2rayN/releases/latest", v2ray)
        self.assertIn("app-download/v2rayn/windows", footer)
        self.assertIn("v2rayng:['android']", footer)
        self.assertIn("singbox:['windows','android','ios','macos']", footer)
        self.assertIn("audited_downloads = global_downloads()", account)
        self.assertNotIn('"/downloads/apps/android/', account)
        self.assertNotIn('"/downloads/apps/windows/', account)
        self.assertNotIn('"/downloads/apps/macos/', account)

    def test_client_name_matches_selected_app(self):
        rows = protocol_client_rows()
        self.assertEqual(rows["v2ray"]["android"][0], "v2rayNG")
        self.assertEqual(rows["v2ray"]["ios"][0], "V2Box")
        self.assertEqual(rows["v2ray"]["windows"][0], "v2rayN")
        self.assertIn("CLI", rows["trusttunnel"]["windows"][0])
        self.assertIn("Homebrew", rows["cisco"]["macos"][0])


if __name__ == "__main__":
    unittest.main()
