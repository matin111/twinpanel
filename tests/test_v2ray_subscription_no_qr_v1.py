"""Regression: V2Ray subscription poll avoids expensive QR SVG work.

The customer Connection Info path still has the exact same QR behavior.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "backend/app/xray_customer_profile_policy_v30.py"
FEED = ROOT / "backend/app/routers/public_connection_multilink_v7.py"


def isolated_policy():
    tree = ast.parse(POLICY.read_text())
    fn = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_customer_xray_item_v261"
    )
    created = []
    def qr(value):
        created.append(value)
        return "svg:" + value
    class Node: pass
    class Db:
        def get(self, kind, key):
            return Node() if key == 7 else None
    scope = {
        "Session": object, "Any": object, "Node": Node,
        "PUBLIC_PROFILE_IDS": {"websocket_tls", "httpupgrade_tls", "tcp_tls"},
        "PUBLIC_PROFILE_ORDER": ("websocket_tls", "httpupgrade_tls", "tcp_tls"),
        "_profile_endpoint_v261": lambda db, node, kind, item: ("v2ray2.in88.sbs", {"websocket_tls":26007, "httpupgrade_tls":27007, "tcp_tls":28007}[kind]),
        "_rewrite_vless_authority_v261": lambda uri, host, port: uri.replace(":9999", ":" + str(port)),
        "account_delivery": SimpleNamespace(_qr_data_uri=qr),
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(POLICY), "exec"), scope)
    return scope["_customer_xray_item_v261"], Db(), created


def example():
    return {
        "node_id": 7,
        "qr": "old-qr",
        "profiles": [
            {"id": key, "uri": "vless://uuid-preserved@v2ray2.in88.sbs:9999?type=tcp#user", "qr":"old-qr"}
            for key in ("websocket_tls", "httpupgrade_tls", "tcp_tls")
        ] + [{"id":"xhttp_reality", "uri":"hidden-profile"}],
    }


class V2raySubscriptionNoQrTests(unittest.TestCase):
    def test_public_feed_skips_svg_generation_but_keeps_three_profiles(self):
        fn, db, created = isolated_policy()
        result = fn(db, example(), include_qr=False)
        self.assertEqual(created, [])
        self.assertEqual([p["id"] for p in result["profiles"]],
                         ["websocket_tls", "httpupgrade_tls", "tcp_tls"])
        self.assertEqual([p["port"] for p in result["profiles"]],
                         [26007,27007,28007])
        self.assertTrue(all("qr" not in p for p in result["profiles"]))
        self.assertNotIn("qr", result)
        self.assertEqual(result["profile"], "websocket_tls")
        self.assertIn("uuid-preserved", result["uri"])

    def test_customer_connection_info_still_generates_every_qr(self):
        fn, db, created = isolated_policy()
        result = fn(db, example())
        self.assertEqual(len(created), 3)
        self.assertTrue(all(p["qr"].startswith("svg:") for p in result["profiles"]))
        self.assertEqual(result["qr"], result["profiles"][0]["qr"])

    def test_every_uri_is_identical_with_and_without_qr(self):
        fn, db, created = isolated_policy()
        with_qr = fn(db, example())
        without_qr = fn(db, example(), include_qr=False)
        self.assertEqual(
            [p["uri"] for p in with_qr["profiles"]],
            [p["uri"] for p in without_qr["profiles"]],
        )
        self.assertEqual(with_qr["uri"], without_qr["uri"])

    def test_public_route_only_uses_qr_free_mode(self):
        src = FEED.read_text()
        tree = ast.parse(src)
        fn = next(
            x for x in tree.body
            if isinstance(x, ast.FunctionDef) and x.name == "_subscription_and_payload"
        )
        body = ast.get_source_segment(src, fn)
        self.assertIn("include_qr=False", body)
        self.assertIn("if delivery_policy.is_explicit_policy", body)
        self.assertIn("account_delivery._public_payload(db, sub)", body)
        self.assertNotIn("db.commit()", body)


if __name__ == "__main__":
    unittest.main()
