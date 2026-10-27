#!/usr/bin/env python3
from __future__ import annotations

import ast
import ipaddress
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "backend/app/naive_tunnel_tls_origin_v274.py"
ACTIVATION_PATH = ROOT / "backend/app/protocol_dataplane_desired_state_v87.py"


def _function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing function: {name}")


def _load_function(source: str, name: str, globals_dict: dict[str, Any]):
    tree = ast.parse(source)
    node = _function_node(tree, name)
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = dict(globals_dict)
    exec(compile(module, str(PATCH_PATH), "exec"), namespace)
    return namespace[name]


def _original_rewrite_stub(result: dict[str, Any], protocol: str, host: str, port: int) -> None:
    outbound = result.get("outbound")
    if isinstance(outbound, dict) and str(outbound.get("type") or "").lower() == protocol:
        outbound = dict(outbound)
        outbound["server"] = host
        outbound["server_port"] = int(port)
        result["outbound"] = outbound

    raw = result.get("config")
    if not isinstance(raw, str) or not raw.strip():
        return
    doc = json.loads(raw)
    changed = False
    for candidate in doc.get("outbounds", []):
        if isinstance(candidate, dict) and str(candidate.get("type") or "").lower() == protocol:
            candidate["server"] = host
            candidate["server_port"] = int(port)
            changed = True
    if changed:
        result["config"] = json.dumps(doc, ensure_ascii=False, indent=2)


def main() -> None:
    source = PATCH_PATH.read_text(encoding="utf-8")
    activation = ACTIVATION_PATH.read_text(encoding="utf-8")

    # Syntax gate for the exact shipped source.
    compile(source, str(PATCH_PATH), "exec")
    compile(activation, str(ACTIVATION_PATH), "exec")

    normalise_san = _load_function(
        source,
        "_normalise_san",
        {"Any": Any, "ipaddress": ipaddress},
    )
    assert normalise_san("193.39.9.222") == "IP:193.39.9.222"
    assert normalise_san("iran.example.test") == "DNS:iran.example.test"

    fake_node_type = SimpleNamespace(EXIT="exit")
    safe_identity = _load_function(
        source,
        "_safe_cert_identity_v274",
        {
            "Any": Any,
            "Node": object,
            "NodeType": fake_node_type,
            "_ORIGINAL_SAFE_CERT_IDENTITY": lambda node: (
                "64.49.12.176",
                ["IP:64.49.12.176"],
            ),
            "_iran_delivery_sans": lambda: ["IP:193.39.9.222"],
        },
    )
    common_name, sans = safe_identity(SimpleNamespace(node_type="exit"))
    assert common_name == "64.49.12.176"
    assert sans == ["IP:64.49.12.176", "IP:193.39.9.222"]

    align = _load_function(
        source,
        "_align_naive_tls_identity",
        {"Any": Any},
    )
    test_outbound = {
        "type": "naive",
        "tls": {"enabled": True, "server_name": "64.49.12.176"},
    }
    assert align(test_outbound, "193.39.9.222") is True
    assert test_outbound["tls"]["server_name"] == "193.39.9.222"

    rewrite = _load_function(
        source,
        "_rewrite_singbox_item_v274",
        {
            "Any": Any,
            "json": json,
            "_ORIGINAL_REWRITE_SINGBOX_ITEM": _original_rewrite_stub,
            "_align_naive_tls_identity": align,
            "naive_tls": SimpleNamespace(MANAGED_NAIVE_TRUST_MODEL="managed-ca-v1"),
        },
    )

    managed = {
        "tls_trust_model": "managed-ca-v1",
        "outbound": {
            "type": "naive",
            "server": "64.49.12.176",
            "server_port": 18447,
            "tls": {
                "enabled": True,
                "server_name": "64.49.12.176",
                "certificate": "managed-ca",
            },
        },
        "config": json.dumps({
            "outbounds": [{
                "type": "naive",
                "server": "64.49.12.176",
                "server_port": 18447,
                "tls": {
                    "enabled": True,
                    "server_name": "64.49.12.176",
                    "certificate": "managed-ca",
                },
            }],
        }),
    }
    rewrite(managed, "naive", "193.39.9.222", 32005)
    assert managed["outbound"]["server"] == "193.39.9.222"
    assert managed["outbound"]["server_port"] == 32005
    assert managed["outbound"]["tls"]["server_name"] == "193.39.9.222"
    managed_config = json.loads(managed["config"])
    assert managed_config["outbounds"][0]["server"] == "193.39.9.222"
    assert managed_config["outbounds"][0]["server_port"] == 32005
    assert managed_config["outbounds"][0]["tls"]["server_name"] == "193.39.9.222"

    custom = {
        "tls_trust_model": "custom-cert-v1",
        "outbound": {
            "type": "naive",
            "server": "64.49.12.176",
            "server_port": 18447,
            "tls": {"enabled": True, "server_name": "naive.example.test"},
        },
        "config": json.dumps({
            "outbounds": [{
                "type": "naive",
                "server": "64.49.12.176",
                "server_port": 18447,
                "tls": {"enabled": True, "server_name": "naive.example.test"},
            }],
        }),
    }
    rewrite(custom, "naive", "193.39.9.222", 32005)
    assert custom["outbound"]["server"] == "193.39.9.222"
    assert custom["outbound"]["tls"]["server_name"] == "naive.example.test"

    tuic = {
        "outbound": {
            "type": "tuic",
            "server": "64.49.12.176",
            "server_port": 8445,
            "tls": {"enabled": True, "server_name": "64.49.12.176"},
        },
        "config": json.dumps({
            "outbounds": [{
                "type": "tuic",
                "server": "64.49.12.176",
                "server_port": 8445,
                "tls": {"enabled": True, "server_name": "64.49.12.176"},
            }],
        }),
    }
    rewrite(tuic, "tuic", "193.39.9.222", 29005)
    assert tuic["outbound"]["server"] == "193.39.9.222"
    assert tuic["outbound"]["tls"]["server_name"] == "64.49.12.176"

    old_call = "    apply_modern_protocol_tunnel_binding_v251()"
    new_call = "    apply_naive_tunnel_tls_origin_v274()"
    assert old_call in activation
    assert new_call in activation
    assert activation.index(old_call) < activation.index(new_call)

    print("NAIVE_TUNNEL_TLS_ORIGIN_V274_SMOKE=PASS")
    print("MANAGED_NAIVE_ENDPOINT_AND_TLS_IDENTITY=PASS")
    print("MANAGED_CERT_EXIT_PLUS_IRAN_SAN=PASS")
    print("CUSTOM_NAIVE_TLS_UNCHANGED=PASS")
    print("NON_NAIVE_TLS_IDENTITY_UNCHANGED=PASS")


if __name__ == "__main__":
    main()
