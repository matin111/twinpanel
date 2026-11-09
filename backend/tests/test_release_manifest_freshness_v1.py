"""Regression tests for CDN-stale release manifests and custom feed isolation."""
from __future__ import annotations

import base64
import json
import unittest
from unittest import mock

from app import system_release as release


def manifest(version, *, published=True):
    return {
        "version": version,
        "published": published,
        "installable": True,
        "channel": "stable",
    }


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def api_envelope(value):
    return {
        "path": "releases/stable.json",
        "encoding": "base64",
        "content": base64.b64encode(json.dumps(value).encode()).decode(),
    }


class ReleaseManifestFreshnessTests(unittest.TestCase):
    def setUp(self):
        release._PUBLIC_API_CACHE = None
        release._PUBLIC_API_CACHE_UNTIL = 0.0
        release._PUBLIC_API_FAILURE_UNTIL = 0.0

    def test_newer_canonical_manifest_wins_over_stale_raw(self):
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            if url == release.OFFICIAL_GITHUB_MANIFEST_API:
                return FakeResponse(api_envelope(manifest("1.1.0-rc.751")))
            return FakeResponse(manifest("1.1.0-rc.750"))

        with mock.patch.dict("os.environ", {
            "TWINPANEL_RELEASE_MANIFEST_URL": release.OFFICIAL_RAW_MANIFEST,
        }), mock.patch.object(release.httpx, "get", side_effect=fetch):
            found = release.release_manifest()
        self.assertEqual(found["version"], "1.1.0-rc.751")
        self.assertEqual(len(calls), 2)

    def test_custom_manifest_never_overridden(self):
        url = "https://customer.example.org/verified-release.json"
        with mock.patch.dict("os.environ", {"TWINPANEL_RELEASE_MANIFEST_URL": url}), \
             mock.patch.object(release.httpx, "get",
                               return_value=FakeResponse(manifest("4.2.0"))) as fetched:
            found = release.release_manifest()
        self.assertEqual(found["version"], "4.2.0")
        fetched.assert_called_once()

    def test_api_failure_keeps_valid_raw_manifest(self):
        def fetch(url, **kwargs):
            if url == release.OFFICIAL_GITHUB_MANIFEST_API:
                raise OSError("rate limit")
            return FakeResponse(manifest("1.1.0-rc.750"))
        with mock.patch.dict("os.environ", {
            "TWINPANEL_RELEASE_MANIFEST_URL": release.OFFICIAL_RAW_MANIFEST,
        }), mock.patch.object(release.httpx, "get", side_effect=fetch):
            self.assertEqual(release.release_manifest()["version"], "1.1.0-rc.750")

    def test_raw_failure_can_recover_from_canonical_api(self):
        def fetch(url, **kwargs):
            if url == release.OFFICIAL_GITHUB_MANIFEST_API:
                return FakeResponse(api_envelope(manifest("1.1.0-rc.751")))
            raise OSError("stale CDN")
        with mock.patch.dict("os.environ", {
            "TWINPANEL_RELEASE_MANIFEST_URL": release.OFFICIAL_RAW_MANIFEST,
        }), mock.patch.object(release.httpx, "get", side_effect=fetch):
            found = release.release_manifest()
        self.assertEqual(found["version"], "1.1.0-rc.751")

    def test_unpublished_api_cannot_override_existing(self):
        def fetch(url, **kwargs):
            if url == release.OFFICIAL_GITHUB_MANIFEST_API:
                return FakeResponse(api_envelope(manifest("1.1.0-rc.752", published=False)))
            return FakeResponse(manifest("1.1.0-rc.750"))
        with mock.patch.dict("os.environ", {
            "TWINPANEL_RELEASE_MANIFEST_URL": release.OFFICIAL_RAW_MANIFEST,
        }), mock.patch.object(release.httpx, "get", side_effect=fetch):
            self.assertEqual(release.release_manifest()["version"], "1.1.0-rc.750")

    def test_canonical_api_is_cached_to_avoid_rate_limits(self):
        calls = []
        def fetch(url, **kwargs):
            calls.append(url)
            if url == release.OFFICIAL_GITHUB_MANIFEST_API:
                return FakeResponse(api_envelope(manifest("1.1.0-rc.751")))
            return FakeResponse(manifest("1.1.0-rc.750"))
        with mock.patch.dict("os.environ", {
            "TWINPANEL_RELEASE_MANIFEST_URL": release.DEFAULT_MANIFEST_URL,
        }), mock.patch.object(release.httpx, "get", side_effect=fetch):
            self.assertEqual(release.release_manifest()["version"], "1.1.0-rc.751")
            self.assertEqual(release.release_manifest()["version"], "1.1.0-rc.751")
        self.assertEqual(calls.count(release.OFFICIAL_GITHUB_MANIFEST_API), 1)


if __name__ == "__main__":
    unittest.main()
