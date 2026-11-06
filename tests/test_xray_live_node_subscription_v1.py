"""Focused regression checks for dynamically rendered V2Ray subscriptions."""
import ast
from pathlib import Path
import unittest
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

SOURCE = Path(__file__).resolve().parents[1] / "backend/app/routers/public_connection_multilink_v7.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"_apply_live_xray_uri", "_v2ray_country_flag", "_v2ray_remark_uri"}]
assert len(functions) == 3
scope = {"parse_qsl": parse_qsl, "quote": quote, "urlencode": urlencode, "urlsplit": urlsplit, "urlunsplit": urlunsplit}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), scope)
apply_uri = scope["_apply_live_xray_uri"]
remark_uri = scope["_v2ray_remark_uri"]


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

    def test_only_username_and_country_flag_in_remark(self):
        raw = "vless://user-secret@iran.example:24007?security=reality&pbk=key&sid=12#old-transport"
        changed = remark_uri(raw, "ali222", "DE")
        self.assertEqual(unquote(urlsplit(changed).fragment), "ali222 🇩🇪")
        self.assertEqual(urlsplit(changed).netloc, urlsplit(raw).netloc)
        self.assertEqual(urlsplit(changed).query, urlsplit(raw).query)

    def test_remarks_are_country_specific(self):
        raw = "vless://u@example.org:443?security=tls#old"
        self.assertEqual(unquote(urlsplit(remark_uri(raw, "ali222", "TR")).fragment), "ali222 🇹🇷")
        self.assertEqual(unquote(urlsplit(remark_uri(raw, "ali222", "US")).fragment), "ali222 🇺🇸")

    def test_unconfigured_or_non_vless_unchanged(self):
        raw = "vless://u@host:24007?security=reality&sni=old.example"
        self.assertEqual(apply_uri(raw, {}), raw)
        self.assertEqual(apply_uri("vmess://foo", {"reality_server_name": "new.example"}), "vmess://foo")


if __name__ == "__main__":
    unittest.main()
