"""Regression for the V47 runtime monkeypatch used by live V2Ray delivery."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
import unittest

ROOT = Path(__file__).resolve().parents[1]
V47 = ROOT / "backend/app/xray_adaptive_three_profiles_v47.py"
FEED = ROOT / "backend/app/routers/public_connection_multilink_v7.py"


def isolated_v47():
    source = V47.read_text()
    tree = ast.parse(source)
    fn = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_customer_xray_item_v47"
    )
    qr_calls = []
    class Node:
        pass
    class Db:
        def get(self, t, node_id):
            return Node() if node_id == 7 else None
    runtime = SimpleNamespace(
        PROFILE_WS="websocket_tls", PROFILE_XHTTP="xhttp_reality",
    )
    v30 = SimpleNamespace(
        _profile_endpoint_v261=lambda db, node, kind, item: (
            "v2ray2.in88.sbs",
            {"websocket_tls":26007, "xhttp_reality":24007, "tcp_tls":28007}[kind],
        ),
        _rewrite_vless_authority_v261=lambda uri, host, port:
            uri.replace(":9999", ":" + str(port)),
    )
    ad = SimpleNamespace(_qr_data_uri=lambda uri: (qr_calls.append(uri), "svg:"+uri)[1])
    symbols = {
        "Any": object, "Node": Node, "xray_modern_runtime": runtime,
        "PROFILE_TCP_TLS":"tcp_tls", "PROFILE_TCP_REALITY":"tcp_reality",
        "_effective_domain": lambda node:"v2ray2.in88.sbs",
        "policy_v30":v30, "account_delivery":ad,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(V47), "exec"), symbols)
    return symbols["_customer_xray_item_v47"], Db(), qr_calls


def fixture():
    return {
        "node_id": 7, "qr": "stale",
        "profiles": [
            {
                "id": kind, "qr":"stale",
                "uri": "vless://uuid-preserved@v2ray2.in88.sbs:9999"
                       "?security=tls&type=ws&path=%2Fkeep#label",
            }
            for kind in ("websocket_tls","xhttp_reality","tcp_tls")
        ] + [{"id":"grpc_reality","uri":"ignored"}],
    }


class XrayV47QrCompat(unittest.TestCase):
    def test_feed_without_qr_preserves_exact_uri_and_three_profiles(self):
        fn, db, made = isolated_v47()
        src = fixture()
        rendered = fn(db, src, include_qr=False)
        self.assertEqual(made, [])
        self.assertEqual(len(rendered["profiles"]), 3)
        self.assertEqual(
            [p["port"] for p in rendered["profiles"]],
            [26007,24007,28007],
        )
        self.assertTrue(all("qr" not in p for p in rendered["profiles"]))
        self.assertNotIn("qr", rendered)
        self.assertEqual(rendered["profile"], "websocket_tls")
        self.assertTrue(all("uuid-preserved" in p["uri"] for p in rendered["profiles"]))
        self.assertEqual(src["qr"], "stale")

    def test_customer_default_still_generates_every_qr(self):
        fn, db, made = isolated_v47()
        rendered = fn(db, fixture())
        self.assertEqual(len(made), 3)
        self.assertEqual(rendered["qr"], rendered["profiles"][0]["qr"])

    def test_qr_flag_never_changes_any_profile_uri(self):
        fn, db, made = isolated_v47()
        with_qr = fn(db, fixture())
        without_qr = fn(db, fixture(), include_qr=False)
        self.assertEqual(
            [p["uri"] for p in with_qr["profiles"]],
            [p["uri"] for p in without_qr["profiles"]],
        )

    def test_runtime_monkeypatch_and_feed_contract(self):
        src = V47.read_text()
        self.assertIn("policy_v30._customer_xray_item_v261 = _customer_xray_item_v47",src)
        self.assertIn("include_qr: bool = True",src)
        feed=FEED.read_text()
        self.assertIn("include_qr=False",feed)
        self.assertNotIn("db.commit()",ast.get_source_segment(
            feed,
            next(x for x in ast.parse(feed).body
                 if isinstance(x,ast.FunctionDef)
                 and x.name=="_subscription_and_payload"
            )
        ))


if __name__ == "__main__":
    unittest.main()
