#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "backend/app/routers/outbound_policy_center_v1.py"
SOURCE = ROUTER.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE, filename=str(ROUTER))


def literal_assignment(name: str):
    for node in TREE.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.target if isinstance(node, ast.AnnAssign) else (node.targets[0] if len(node.targets) == 1 else None)
            if isinstance(target, ast.Name) and target.id == name:
                value = node.value
                return ast.literal_eval(value)
    raise AssertionError(f"assignment not found: {name}")


native = literal_assignment("_NATIVE_POLICY_PROTOCOLS")
xray_profiles = literal_assignment("_XRAY_PROFILE_PROTOCOLS")

expected_native = {
    "hysteria2": "twinpanel-hysteria2-in",
    "tuic": "twinpanel-tuic-in",
    "anytls": "twinpanel-anytls-in",
    "naive": "twinpanel-naive-in",
    "shadowtls": "twinpanel-shadowtls-inner",
    "snell": "twinpanel-snell-in",
}
assert native == expected_native, native

expected_profiles = {
    "vless_ws_tls": "websocket_tls",
    "vless_httpupgrade_tls": "httpupgrade_tls",
    "vless_tcp_tls": "tcp_tls",
    "vless_xhttp_reality": "xhttp_reality",
    "vless_grpc_reality": "grpc_reality",
    "vless_tcp_simple": "tcp_simple",
    "vless_legacy": "legacy",
}
assert {key: value["profile"] for key, value in xray_profiles.items()} == expected_profiles

# The 15 canonical top-level protocols plus seven audited Xray/VLESS profile
# rows must produce 22 visible Policy Center rows. The seven profiles are
# intentionally display-only until a real Xray egress adapter is implemented.
assert "*_XRAY_PROFILE_PROTOCOLS.keys()" in SOURCE
assert '"policy_supported": False' in SOURCE
assert '"reason": "separate_core_adapter_required"' in SOURCE
assert '"profile": spec.get("profile")' in SOURCE

# Safety contract: ShadowTLS routes payload after the camouflage layer via the
# internal Shadowsocks inbound, never the outer ShadowTLS listener.
assert native["shadowtls"] != "twinpanel-shadowtls-in"

print("OUTBOUND_POLICY_PROTOCOL_INVENTORY_V250_SMOKE=PASS")
print("NATIVE_ROUTE_READY_COUNT=6")
print("XRAY_PROFILE_COUNT=7")
print("EXPECTED_PROTOCOL_INVENTORY_COUNT=22")
