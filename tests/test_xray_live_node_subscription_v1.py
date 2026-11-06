"""Focused regression checks for dynamically rendered V2Ray subscriptions."""
import ast
import re
from pathlib import Path
import unittest
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

SOURCE = Path(__file__).resolve().parents[1] / "backend/app/routers/public_connection_multilink_v7.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"_apply_live_xray_uri", "_v2ray_country_flag", "_v2ray_remark_uri"}]
assert len(functions) == 3
scope = {"Any": Any, "_HOSTNAME": re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$"), "parse_qsl": parse_qsl, "quote": quote, "urlencode": urlencode, "urlsplit": urlsplit, "urlunsplit": urlunsplit}
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

    def test_websocket_path_without_global_sni_change(self):
        raw="vless://u@edge:443?security=tls&type=ws&sni=old.example&host=old.example&path=%2Fold"
        updated=apply_uri(raw,{"inbound_applied":{"ws_tls":{"path":"/ws-new-validated"}}})
        query=dict(parse_qsl(urlsplit(updated).query))
        self.assertEqual(query["path"],"/ws-new-validated")
        self.assertEqual(query["sni"],"old.example")

    def test_independent_tls_names(self):
        settings={"inbound_applied":{"tcp_tls":{"server_name":"tcp.example.org"},"ws_tls":{"server_name":"ws.example.org"}}}
        tcp=apply_uri("vless://u@edge:443?type=tcp&security=tls&sni=old.example",settings)
        ws=apply_uri("vless://u@edge:444?type=ws&security=tls&sni=old.example&host=old.example",settings)
        self.assertEqual(dict(parse_qsl(urlsplit(tcp).query))["sni"],"tcp.example.org")
        self.assertEqual(dict(parse_qsl(urlsplit(ws).query))["sni"],"ws.example.org")

    def test_xhttp_path_preserves_identity(self):
        raw="vless://uuid@edge:24007?type=xhttp&security=reality&sni=old.example&pbk=pub&sid=short&path=%2Foldpath"
        result=apply_uri(raw,{"reality_server_name":"new.example","inbound_applied":{"xhttp_reality":{"path":"/xhttp-validated"}}})
        self.assertEqual(urlsplit(result).netloc,urlsplit(raw).netloc)
        query=dict(parse_qsl(urlsplit(result).query))
        self.assertEqual((query["sni"],query["path"],query["pbk"],query["sid"]),("new.example","/xhttp-validated","pub","short"))

    def test_connection_domain_alias_changes_host_not_credentials(self):
        raw="vless://uuid-example@old-ingress.example:24007?type=xhttp&security=reality&pbk=publickey&sid=shortid"
        updated=apply_uri(raw,{"inbound_applied":{"xhttp_reality":{"connection_domain":"alias.example"}}})
        self.assertEqual(urlsplit(updated).netloc,"uuid-example@alias.example:24007")
        self.assertEqual(urlsplit(updated).query,urlsplit(raw).query)

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
