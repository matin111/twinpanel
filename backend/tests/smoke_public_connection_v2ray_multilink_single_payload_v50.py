from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "backend/app/routers/public_connection_v2ray_multilink_v43.py"
source = TARGET.read_text(encoding="utf-8")
module_ast = ast.parse(source)


def function_node(name: str) -> ast.FunctionDef:
    for node in module_ast.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing function: {name}")


node = function_node("_delivery_v43")
segment = ast.get_source_segment(source, node) or ""

# Regression contract: V2Ray delivery must build the active customer payload
# exactly once. _active() already resolves runtime-patched stored_info, including
# V30/V47 customer profile policy, Mother filtering and explicit delivery hooks.
assert "sub, payload = multilink._active(token, db)" in segment
assert "_public_payload_customer_xray" not in segment
assert "_legacy_payload" not in segment

# The endpoint must still extract all V2Ray items and all customer-safe profiles
# after the single payload pass.
assert 'multilink._protocol_items(payload, "v2ray")' in segment
assert '_all_share_uris_v43(sub, "v2ray", items)' in segment
assert 'return "uri", len(items), sub, items, uris' in segment

# Guard the production marker used during acceptance/audit.
assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MULTILINK_SINGLE_PAYLOAD_V50" in source

# Scope guard: this latency fix must remain delivery-only.
for forbidden in (
    "iptables",
    "nft ",
    "vxlan",
    "tp27",
    "quota",
    "accounting",
    "provision",
    "credential generation",
    "firewall",
):
    assert forbidden not in segment.lower(), forbidden

print("Public Connect V2Ray Multi-Link single-payload V50 smoke: PASS")
