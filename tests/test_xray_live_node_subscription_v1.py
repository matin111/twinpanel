"""Focused regression checks for dynamically rendered V2Ray subscriptions."""
import ast
from pathlib import Path
import unittest
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SOURCE = Path(__file__).resolve().parents[1] / "backend/app/routers/public_connection_multilink_v7.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_apply_live_xray_uri"]
assert len(functions) == 1
scope = {"parse_qsl": parse_qsl, "urlencode": urlencode, "urlsplit": urlsplit, "urlunsplit": urlunsplit}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), scope)
apply_uri = scope["_apply_live_xray_uri"]


class LiveXrayUriTests(unittest.TestCase):
    def test_reality_sni_updated_without_changing_secret_or_authority(self):
        raw = "vless://uuid123@iran.example:24007?security=reality&type=xhttp&sni=www.microsoft.com&pbk=oldpub&sid=oldshort&path=%2Fxh"
        actual = apply_uri(raw, {"reality_server_name": "www.varzesh3.com"})
        assert urlsplit(actual).netloc == "uuid123@iran.example:24007"
        query = dict(parse_qsl(urlsplit(actual).query))
        self.assertEqual(query["sni"], "www.varzesh3.com")
        self.assertEqual(query["pbk"], "oldpub")
        self.assertEqual(query["sid"], "oldshort")
        self.assertEqual(query["path"], "/xh")

    def test_tls_does_not_inherit_reality(self):
        raw = "vless://u@host:28007?security=tls&sni=v2ray2.in88.sbs&host=v2ray2.in88.sbs"
        self.assertEqual(apply_uri(raw, {"reality_server_name": "www.varzesh3.com"}), raw)

    def test_tls_updates_sni_and_host(self):
        raw = "vless://u@host:26007?security=tls&type=ws&sni=old.example&host=old.example"
        value = apply_uri(raw, {"tls_server_name": "new.example"})
        q = dict(parse_qsl(urlsplit(value).query))
        self.assertEqual((q["sni"], q["host"]), ("new.example", "new.example"))
        self.assertEqual(urlsplit(value).hostname, "host")

    def test_unconfigured_or_non_vless_unchanged(self):
        raw = "vless://u@host:24007?security=reality&sni=old.example"
        self.assertEqual(apply_uri(raw, {}), raw)
        self.assertEqual(apply_uri("vmess://foo", {"reality_server_name": "new.example"}), "vmess://foo")


if __name__ == "__main__":
    unittest.main()
