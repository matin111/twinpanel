"""Regression checks: release updater must reject stale/missing V2Ray feeds."""
import base64
import importlib.util
from pathlib import Path
from unittest.mock import patch

UPDATER = Path(__file__).resolve().parents[1] / "scripts/twinpanel_public_updater_v69.py"


def _module():
    spec = importlib.util.spec_from_file_location("updater_canary_test", UPDATER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, status, content):
        self.status = status
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=-1):
        return self.content[:n]


def test_matching_feeds_accept():
    module = _module()
    content = base64.b64encode(b"vless://example@x:443#test")
    calls = []

    def get(request, timeout):
        calls.append(request.full_url)
        return _Response(200, content)

    with patch.object(module.urllib.request, "urlopen", side_effect=get):
        assert module._v2ray_feed_canary(8095, "valid-test-token")
    assert len(calls) == 2
    assert calls[0].endswith("/sub") and calls[1].endswith("/multi/v2ray")


def test_bad_or_different_feed_rejected():
    module = _module()
    good = base64.b64encode(b"vless://example@x:443#a")
    other = base64.b64encode(b"vless://example@x:443#b")
    for responses in (
        [(200, good), (200, other)],
        [(503, b""), (200, good)],
        [(200, base64.b64encode(b"")), (200, good)],
        [(200, b"<html>broken</html>"), (200, good)],
    ):
        iterator = iter(responses)
        with patch.object(module.urllib.request, "urlopen", side_effect=lambda *a, **k: _Response(*next(iterator))):
            assert not module._v2ray_feed_canary(8095, "valid-test-token")


def test_invalid_token_does_not_make_request():
    module = _module()
    with patch.object(module.urllib.request, "urlopen") as request:
        assert not module._v2ray_feed_canary(8095, "../../wrong")
        request.assert_not_called()
