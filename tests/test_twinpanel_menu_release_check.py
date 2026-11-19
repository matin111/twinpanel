"""Regression tests for fast terminal release checks (no app import)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path


SOURCE = Path(__file__).with_name("twinpanel_menu_release_check.py")
if not SOURCE.is_file():
    SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "twinpanel_menu_release_check.py"
spec = importlib.util.spec_from_file_location("twinpanel_menu_release_check", SOURCE)
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class FastReleaseCheckTests(unittest.TestCase):
    def test_import_does_not_load_app(self):
        self.assertNotIn("app", sys.modules)

    def test_version_order_preserves_rc_to_stable_upgrade(self):
        self.assertGreater(release.version_key("1.1.0"), release.version_key("1.1.0-rc.775"))
        self.assertGreater(release.version_key("1.1.1-beta.1"), release.version_key("1.1.0"))

    def test_official_feed_reports_newer_version(self):
        seen = []

        def runner(args, **kwargs):
            seen.append((args[-1], kwargs["timeout"]))
            return subprocess.CompletedProcess(args, 0, b'{"version":"1.1.1","published":true,"installable":true}')

        self.assertEqual(release.check_release("1.1.0", "", runner), ("1.1.1", "AVAILABLE"))
        self.assertEqual(seen, [(release.OFFICIAL_RAW_MANIFEST, release.HTTP_TIMEOUT_SECONDS + 1.0)])

    def test_custom_feed_is_not_redirected_to_public_feed(self):
        seen = []

        def runner(args, **kwargs):
            seen.append(args[-1])
            return subprocess.CompletedProcess(args, 0, b'{"version":"1.1.0","published":true}')

        self.assertEqual(release.check_release("1.1.0", "https://example.org/release.json", runner), ("1.1.0", "up to date"))
        self.assertEqual(seen, ["https://example.org/release.json"])

    def test_offline_feed_does_not_claim_up_to_date(self):
        def offline(args, **kwargs):
            return subprocess.CompletedProcess(args, 28, b"")

        self.assertEqual(release.check_release("1.1.0", "", offline), (None, "check unavailable"))

    def test_bad_unpublished_manifest_is_rejected(self):
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, b'{"version":"9.9.9","published":false}')

        self.assertEqual(release.check_release("1.1.0", "", runner), (None, "check unavailable"))

    def test_manifest_size_limit(self):
        def oversized(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, b" " * (release.MAX_MANIFEST_BYTES + 10))

        self.assertEqual(release.check_release("1.1.0", "", oversized), (None, "check unavailable"))


class TerminalBrandTests(unittest.TestCase):
    def test_large_banner_spells_twinpanel(self):
        menu = SOURCE.with_name("twinpanel-menu.sh")
        if not menu.is_file():
            menu = SOURCE.with_name("twinpanel-menu.patched.sh")
        script = menu.read_text(encoding="utf-8")
        brand = re.search(r"^brand\(\)\{\n(.*?)^\}", script, flags=re.M | re.S)
        self.assertIsNotNone(brand)
        rows = re.findall(r"^\s*brand_row (.*)$", brand.group(1), flags=re.M)
        self.assertEqual(len(rows), 7)
        columns = [re.findall(r"'([01]{5})'", row) for row in rows]
        self.assertTrue(all(len(row) == 9 for row in columns))
        letters = ["".join(columns[row][col] for row in range(7)) for col in range(9)]
        expected = {
            "T": "11111001000010000100001000010000100",
            "W": "10001100011000110101101011010101010",
            "I": "11111001000010000100001000010011111",
            "N": "10001110011010110011100011000110001",
            "P": "11110100011000111110100001000010000",
            "A": "01110100011000111111100011000110001",
            "E": "11111100001000011110100001000011111",
            "L": "10000100001000010000100001000011111",
        }
        self.assertEqual(letters, [expected[ch] for ch in "TWINPANEL"])


if __name__ == "__main__":
    unittest.main()
