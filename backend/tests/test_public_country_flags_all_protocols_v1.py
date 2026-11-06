"""Public config remark country flags across supported protocol families.

Display-only: do not change native WireGuard/OpenVPN file naming or
subscription credentials.
"""
from __future__ import annotations

import ast
import re
import secrets
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "app" / "routers"
names_src = (ROUTERS / "public_connection_modern_names_v14.py").read_text(encoding="utf-8")
hub_src = (ROUTERS / "public_connection_hub_v5.py").read_text(encoding="utf-8")
delivery_src = (ROUTERS / "account_delivery.py").read_text(encoding="utf-8")

for source in (names_src, hub_src, delivery_src):
    compile(source, "<country-flags>", "exec")

tree = ast.parse(names_src)
helper_set = {"_safe_component", "_account_name", "_node_name", "_country_flag", "_profile_name", "_download_stem"}
nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in helper_set]
scope = {
    "Any": Any,
    "re": re,
    "secrets": secrets,
    "_ALLOWED_COMPONENT": re.compile(r"[^A-Za-z0-9_=+.-]+"),
}
exec(compile(ast.Module(body=nodes, type_ignores=[]), "<country-flags>", "exec"), scope)

sub = SimpleNamespace(id=19, account_username="ALI222")
countries = {"DE": "🇩🇪", "FR": "🇫🇷", "TR": "🇹🇷", "NL": "🇳🇱"}
protocols = (
    "openvpn", "wireguard", "amneziawg", "v2ray", "anytls", "hysteria2",
    "tuic", "naive", "shadowtls", "snell", "mieru", "trusttunnel",
    "sudoku", "socks5", "cisco", "l2tp",
)


def test_country_flags_for_every_supported_protocol_remark():
    for code, flag in countries.items():
        item = {"node_id": 13, "node": "Germany-13", "country_code": code}
        for protocol in protocols:
            name = scope["_profile_name"](sub, protocol, item)
            assert name == f"ALI222 {flag} {protocol}-13"
            assert "Germany" not in name
        # Native file extensions are not part of the display name.
        filename = scope["_download_stem"](sub, "wireguard", item)
        assert filename.isascii()
        assert "🇩🇪" not in filename


def test_unknown_country_does_not_fake_a_flag():
    item = {"node_id": 13, "node": "CustomNode"}
    assert scope["_profile_name"](sub, "tuic", item) == "ALI222-CustomNode-tuic-13"
    assert scope["_country_flag"]("WRONG") == "🌐"


def test_authoritative_country_origin_and_page_flag_rendering():
    assert 'item["country_code"] = code' in delivery_src
    assert 'str(node.country_code or "").strip().upper()' in delivery_src
    assert "_attach_node_country_codes(db, data)" in delivery_src
    assert 'item.get("country_code")' in hub_src
    assert "node_id or index + 1" in hub_src


def test_new_node_and_country_change_are_read_from_live_database_each_time():
    # Execute the pure metadata enrichment helper with a mocked ORM registry,
    # including a node added AFTER the first request, without migrations.
    class Query:
        def __init__(self, registry):
            self.registry = registry
        def filter(self, _predicate):
            return self
        def all(self):
            return list(self.registry.values())

    class Registry:
        def __init__(self):
            self.nodes = {13: SimpleNamespace(id=13, country_code="DE")}
        def query(self, _model):
            return Query(self.nodes)

    class Column:
        def in_(self, _values):
            return True

    class NodeMock:
        id = Column()

    ast_tree = ast.parse(delivery_src)
    helper = next(node for node in ast_tree.body if isinstance(node, ast.FunctionDef) and node.name == "_attach_node_country_codes")
    scope = {"Session": Any, "Node": NodeMock, "Any": Any}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "<delivery-flags>", "exec"), scope)
    enrich = scope["_attach_node_country_codes"]
    registry = Registry()
    first = [{"protocol": "tuic", "items": [{"node_id": 13}]}]
    enrich(registry, first)
    assert first[0]["items"][0]["country_code"] == "DE"

    registry.nodes[19] = SimpleNamespace(id=19, country_code="FR")
    later = [{"protocol": protocol, "items": [{"node_id": 19}]} for protocol in ("tuic", "openvpn", "wireguard", "v2ray", "socks5")]
    enrich(registry, later)
    assert {row["items"][0]["country_code"] for row in later} == {"FR"}
    for row in later:
        assert "🇫🇷" in scope["_profile_name"](sub, row["protocol"], row["items"][0])

    registry.nodes[19].country_code = "TR"
    refreshed = [{"protocol": "snell", "items": {"node_id": 19}}]
    enrich(registry, refreshed)
    assert refreshed[0]["items"]["country_code"] == "TR"
    assert "🇹🇷" in scope["_profile_name"](sub, "snell", refreshed[0]["items"])
