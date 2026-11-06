"""Keep existing VLESS client identities while refreshing applied XHTTP SNI."""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
from sys import path as sys_path
sys_path.insert(0, str(ROOT / "backend"))
from app.xray_live_reality_sni_delivery_v1 import (
    applied_reality_snis,
    rewrite_reality_sni_item,
)


def fixture() -> dict:
    base = "vless://uuid-preserved@v2ray2.in88.sbs"
    ws = base + ":26007?type=ws&security=tls&sni=v2ray2.in88.sbs&path=%2Fws%2F123#WS"
    xhttp = (
        base + ":24007?encryption=none&security=reality&type=xhttp"
        "&path=%2Fxhttp%2Fabc%3D&mode=stream-one&sni=www.microsoft.com"
        "&fp=chrome&pbk=public-key-preserved&sid=short-id-preserved#XHTTP"
    )
    tcp = base + ":28007?type=tcp&security=tls&sni=v2ray2.in88.sbs#TCP"
    return {
        "node_id": 7, "profile": "websocket_tls", "uri": ws,
        "profiles": [
            {"id": "websocket_tls", "uri": ws},
            {"id": "xhttp_reality", "uri": xhttp, "sni": "www.microsoft.com",
             "qr": "old-qr-must-not-be-used"},
            {"id": "tcp_tls", "uri": tcp},
        ],
    }


class VerifiedRealitySniTests(unittest.TestCase):
    def test_central_settings_are_read_only_and_require_matching_target(self):
        class FakeSession:
            def execute(self, stmt):
                self.sql = str(stmt)
                class Result:
                    def all(self):
                        return [
                            (7, json.dumps({"reality_server_name":"www.varzesh3.com",
                                            "reality_target":"www.varzesh3.com:443"})),
                            (6, json.dumps({"reality_server_name":"www.microsoft.com",
                                            "reality_target":"www.google.com:443"})),
                            (11, {"draft":{"reality_server_name":"bad.example.com"}}),
                        ]
                return Result()
        db = FakeSession()
        self.assertEqual(applied_reality_snis(db), {7:"www.varzesh3.com"})
        self.assertIn("SELECT node_id, settings_json", db.sql)

    def test_only_xhttp_sni_rewritten_all_other_uri_bytes_preserved(self):
        old = fixture()
        snapshot = copy.deepcopy(old)
        updated = rewrite_reality_sni_item(old, "www.varzesh3.com")
        self.assertEqual(old, snapshot)
        self.assertEqual(updated["uri"], old["uri"])
        self.assertIs(updated["profiles"][0], old["profiles"][0])
        self.assertIs(updated["profiles"][2], old["profiles"][2])
        old_uri = old["profiles"][1]["uri"]
        new_uri = updated["profiles"][1]["uri"]
        self.assertEqual(
            new_uri,
            old_uri.replace("sni=www.microsoft.com", "sni=www.varzesh3.com")
        )
        self.assertNotIn("qr", updated["profiles"][1])
        self.assertEqual(updated["profiles"][1]["sni"], "www.varzesh3.com")
        self.assertEqual(
            parse_qs(urlsplit(new_uri).query)["mode"], ["stream-one"]
        )
        self.assertEqual(urlsplit(new_uri).username, urlsplit(old_uri).username)
        self.assertEqual(urlsplit(new_uri).port, urlsplit(old_uri).port)
        self.assertEqual(urlsplit(new_uri).fragment, urlsplit(old_uri).fragment)

    def test_primary_xhttp_uri_gets_correct_sni(self):
        item = fixture()
        item["uri"] = item["profiles"][1]["uri"]
        item["qr"] = "legacy-qr"
        updated = rewrite_reality_sni_item(item, "www.varzesh3.com")
        self.assertIn("sni=www.varzesh3.com", updated["uri"])
        self.assertNotIn("qr", updated)
        self.assertEqual(updated["sni"], "www.varzesh3.com")

    def test_unverified_or_duplicate_query_rejected_without_changes(self):
        item = fixture()
        for candidate in ("", "not-a-host", "a..b.com", "www.example.com:443"):
            self.assertIs(rewrite_reality_sni_item(item, candidate), item)
        duplicate = copy.deepcopy(item)
        old_uri = duplicate["profiles"][1]["uri"]
        payload, fragment = old_uri.split("#", 1)
        duplicate["profiles"][1]["uri"] = (
            payload + "&sni=duplicate.example.com#" + fragment
        )
        self.assertIs(rewrite_reality_sni_item(duplicate, "www.varzesh3.com"), duplicate)

    def test_public_delivery_uses_applied_names_before_items_are_published(self):
        source = (ROOT / "backend/app/routers/account_delivery.py").read_text()
        tree = ast.parse(source)
        fn = next(
            x for x in tree.body
            if isinstance(x, ast.FunctionDef) and x.name == "_stored_info"
        )
        body = ast.get_source_segment(source, fn)
        self.assertIn("applied_reality_snis(db)", body)
        self.assertIn("rewrite_reality_sni_item(", body)
        self.assertLess(body.index("rewrite_reality_sni_item("),
                        body.index("_delivery_item_is_usable("))
        self.assertNotIn("config_text_encrypted = ", body)


if __name__ == "__main__":
    unittest.main()
