"""Regression tests for fast terminal release checks (no app import)."""

from __future__ import annotations

import importlib.util
import io
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


class FakeResponse:
    def __init__(self, data: bytes):
        self.data = io.BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, size: int):
        return self.data.read(size)


class FastReleaseCheckTests(unittest.TestCase):
    def test_import_does_not_load_app(self):
        self.assertNotIn("app", sys.modules)

    def test_version_order_preserves_rc_to_stable_upgrade(self):
        self.assertGreater(release.version_key("1.1.0"), release.version_key("1.1.0-rc.775"))
        self.assertGreater(release.version_key("1.1.1-beta.1"), release.version_key("1.1.0"))

    def test_official_feed_reports_newer_version(self):
        seen = []

        def opener(req, timeout):
            seen.append((req.full_url, timeout))
            return FakeResponse(b'{"version":"1.1.1","published":true,"installable":true}')

        self.assertEqual(release.check_release("1.1.0", "", opener), ("1.1.1", "AVAILABLE"))
        self.assertEqual(seen, [(release.OFFICIAL_RAW_MANIFEST, release.HTTP_TIMEOUT_SECONDS)])

    def test_custom_feed_is_not_redirected_to_public_feed(self):
        seen = []

        def opener(req, timeout):
            seen.append(req.full_url)
            return FakeResponse(b'{"version":"1.1.0","published":true}')

        self.assertEqual(release.check_release("1.1.0", "https://example.org/release.json", opener), ("1.1.0", "up to date"))
        self.assertEqual(seen, ["https://example.org/release.json"])

    def test_offline_feed_does_not_claim_up_to_date(self):
        def offline(req, timeout):
            raise OSError("offline")

        self.assertEqual(release.check_release("1.1.0", "", offline), (None, "check unavailable"))

    def test_bad_unpublished_manifest_is_rejected(self):
        def opener(req, timeout):
            return FakeResponse(b'{"version":"9.9.9","published":false}')

        self.assertEqual(release.check_release("1.1.0", "", opener), (None, "check unavailable"))

    def test_manifest_size_limit(self):
        def oversized(req, timeout):
            return FakeResponse(b" " * (release.MAX_MANIFEST_BYTES + 10))

        self.assertEqual(release.check_release("1.1.0", "", oversized), (None, "check unavailable"))


if __name__ == "__main__":
    unittest.main()
