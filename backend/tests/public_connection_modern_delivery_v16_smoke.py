from __future__ import annotations

import ast
import copy
import html
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "backend" / "app" / "routers"

v16_path = ROUTERS / "public_connection_modern_delivery_v16.py"
live_path = ROUTERS / "public_connection_hub_live_v5.py"

v16 = v16_path.read_text(encoding="utf-8")
live = live_path.read_text(encoding="utf-8")

compile(v16, str(v16_path), "exec")
compile(live, str(live_path), "exec")

for marker in (
    "TWINPANEL_PUBLIC_MODERN_DELIVERY_V16",
    'router.get("/{token}/modern-config-v16/{protocol}/{node_id}")',
    "def _resolve_delivery_content(",
    "def _replace_unsupported_karing_button(",
    "برای این سرور هنوز کانفیگ قابل تحویل ساخته نشده است",
):
    assert marker in v16, marker

# V16 must be mounted and run strictly after V15, preserving the accepted chain.
assert "public_connection_modern_delivery_v16_router" in live
assert "router.include_router(public_connection_modern_delivery_v16_router)" in live
assert live.index("refine_public_connection_modern_import_v15(source, token, db)") < live.index(
    "refine_public_connection_modern_delivery_v16(source, token, db)"
)

# Execute only pure helpers without importing the application stack.
tree = ast.parse(v16)
helper_names = {
    "_h",
    "_resolve_delivery_content",
    "_replace_unsupported_karing_button",
}
helper_nodes = [
    node
    for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name in helper_names
]
module = ast.Module(body=helper_nodes, type_ignores=[])
ast.fix_missing_locations(module)


def fake_outbound(item: dict[str, Any]) -> dict[str, Any] | None:
    outbound = item.get("outbound")
    return copy.deepcopy(outbound) if isinstance(outbound, dict) else None


namespace: dict[str, Any] = {
    "Any": Any,
    "copy": copy,
    "html": html,
    "json": json,
    "re": re,
    "_outbound": fake_outbound,
    "KARING_126_PROTOCOLS": {"snell", "sudoku", "trusttunnel"},
}
exec(compile(module, str(v16_path), "exec"), namespace)

resolve = namespace["_resolve_delivery_content"]
replace_karing = namespace["_replace_unsupported_karing_button"]

# Naive raw JSON must win even if a URI/outbound also exists, because the raw
# client config carries the managed CA certificate/trust material.
naive_raw = json.dumps(
    {
        "outbounds": [
            {
                "type": "naive",
                "server": "204.10.192.96",
                "server_port": 8447,
                "tls": {
                    "enabled": True,
                    "certificate": "-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----\n",
                },
            }
        ]
    }
)
naive = {
    "config": naive_raw,
    "config_format": "sing-box",
    "uri": "naive://lossy-example",
    "outbound": {"type": "naive", "server": "204.10.192.96"},
}
content, ext, media = resolve("naive", naive, "user-tr-naive-6")
assert content == naive_raw
assert "BEGIN CERTIFICATE" in content
assert ext == "json"
assert media == "application/json"

# Stored canonical URI is the first fallback when raw config is absent.
uri_item = {
    "config": "",
    "uri": "snell://canonical-share",
    "outbound": {"type": "snell", "server": "203.0.113.7", "server_port": 443},
}
content, ext, media = resolve("snell", uri_item, "user-tr-snell-6")
assert content == "snell://canonical-share"
assert ext == "txt" and media == "text/plain"

# If neither raw config nor URI exists, serialize only the canonical outbound
# already produced by Account Delivery. No protocol-specific fields are invented.
for protocol in ("snell", "trusttunnel", "sudoku", "amneziawg"):
    item = {
        "config": "",
        "uri": "",
        "outbound": {
            "type": protocol,
            "server": "203.0.113.9",
            "server_port": 9443,
            "password": "existing-secret",
        },
    }
    content, ext, media = resolve(protocol, item, f"user-tr-{protocol}-6")
    payload = json.loads(content)
    assert payload == {
        "outbounds": [
            {
                "type": protocol,
                "server": "203.0.113.9",
                "server_port": 9443,
                "password": "existing-secret",
                "tag": f"user-tr-{protocol}-6",
            }
        ]
    }
    assert ext == "json" and media == "application/json"

# No raw config, URI, or outbound remains fail-closed with no fabricated data.
assert resolve("snell", {"config": "", "uri": ""}, "user-snell") is None

# Karing 1.2.25 must not keep the V13 one-click button for the 1.2.26-only
# cohort. It becomes a real download action while direct-supported protocols are untouched.
old_path = "/v1/connect/t/modern-config-v16/trusttunnel/6"
source = (
    '<div class="v13-modern-action" data-v13-protocol="trusttunnel">'
    '<div class="v13-action-buttons">'
    '<button class="primary-btn v13-karing-import" type="button" '
    f'data-config-path="{old_path}" data-config-name="user-tr-trusttunnel-6">'
    'افزودن مستقیم به Karing</button></div></div>'
)
fixed = replace_karing(
    source,
    protocol="trusttunnel",
    config_path=old_path,
)
assert "v13-karing-import" not in fixed
assert "tp-v16-safe-download" in fixed
assert f'href="{old_path}"' in fixed

unchanged = replace_karing(
    source.replace("trusttunnel", "hysteria2"),
    protocol="hysteria2",
    config_path=old_path.replace("trusttunnel", "hysteria2"),
)
assert "v13-karing-import" in unchanged

print("PUBLIC_CONNECTION_MODERN_DELIVERY_V16_SMOKE=PASS")
print("RAW_CONFIG_PRECEDENCE=PASS")
print("URI_FALLBACK=PASS")
print("OUTBOUND_FALLBACK=snell-trusttunnel-sudoku-amneziawg")
print("KARING_125_GUARD=PASS")
print("NO_FABRICATED_CONFIG=PASS")
