from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlsplit


ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "backend" / "app" / "routers"

v15_path = ROUTERS / "public_connection_modern_import_v15.py"
live_path = ROUTERS / "public_connection_hub_live_v5.py"

v15 = v15_path.read_text(encoding="utf-8")
live = live_path.read_text(encoding="utf-8")

compile(v15, str(v15_path), "exec")
compile(live, str(live_path), "exec")

for marker in (
    "TWINPANEL_PUBLIC_MODERN_IMPORT_V15",
    "karing://install-config?url=",
    "data-tp-copy-target",
    "tp-v15-app-launch",
    "tp-v15-classic-copy",
    "کپی کانفیگ",
    '"hysteria2"',
    '"tuic"',
    '"anytls"',
    '"naive"',
    '"shadowtls"',
    '"mieru"',
    "def karing_inline_uri(",
    "def standard_share_uri(",
    "def _copy_content(",
):
    assert marker in v15, marker

assert "ulink://install/?content=" not in v15

# V15 remains the final delivery refinement after accepted V13/V14.
assert "refine_public_connection_modern_import_v15" in live
assert live.index("refine_public_connection_modern_names_v14(source, token, db)") < live.index(
    "refine_public_connection_modern_import_v15(source, token, db)"
)

# Execute pure helpers without importing the application stack.
tree = ast.parse(v15)
helper_names = {
    "_host_for_uri",
    "_outbound",
    "_tls_params",
    "standard_share_uri",
    "_copy_content",
    "karing_inline_uri",
}
helper_nodes = [
    node
    for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name in helper_names
]
module = ast.Module(body=helper_nodes, type_ignores=[])
ast.fix_missing_locations(module)


def fake_mieru(item: dict[str, Any]) -> str:
    return "proxies:\n  - name: \"TwinPanel Mieru\"\n    type: mieru\n"


def fake_sudoku(item: dict[str, Any]) -> str:
    return "sudoku://TEST"


namespace: dict[str, Any] = {
    "Any": Any,
    "copy": copy,
    "json": json,
    "quote": quote,
    "urlencode": urlencode,
    "_mieru_karing_yaml": fake_mieru,
    "_sudoku_uri": fake_sudoku,
    "KARING_DIRECT_PROTOCOLS": {
        "hysteria2",
        "tuic",
        "anytls",
        "naive",
        "shadowtls",
        "mieru",
    },
    "STANDARD_SHARE_PROTOCOLS": {
        "hysteria2",
        "tuic",
        "anytls",
    },
}
exec(compile(module, str(v15_path), "exec"), namespace)

karing_inline_uri = namespace["karing_inline_uri"]
standard_share_uri = namespace["standard_share_uri"]
copy_content = namespace["_copy_content"]

hysteria_item = {
    "outbound": {
        "type": "hysteria2",
        "tag": "twinpanel-hysteria2",
        "server": "204.10.192.96",
        "server_port": 8444,
        "password": "hy2 pass+/=",
        "obfs": {"type": "salamander", "password": "obfs secret"},
        "tls": {
            "enabled": True,
            "server_name": "204.10.192.96",
            "insecure": True,
        },
    }
}

hy2_share = standard_share_uri(
    "hysteria2",
    hysteria_item,
    "MV17-14-tr-hysteria2-6",
)
assert hy2_share.startswith("hysteria2://")
assert "insecure=1" in hy2_share
assert "obfs=salamander" in hy2_share
assert "obfs-password=obfs+secret" in hy2_share

hy2_karing = karing_inline_uri(
    "hysteria2",
    hysteria_item,
    "MV17-14-tr-hysteria2-6",
)
assert hy2_karing.startswith("karing://install-config?url=")
parts = urlsplit(hy2_karing)
params = parse_qs(parts.query)
assert params["name"] == ["MV17-14-tr-hysteria2-6"]
assert params["url"] == [hy2_share]
assert "http://217." not in hy2_karing
assert "/modern-config" not in hy2_karing


tuic_item = {
    "outbound": {
        "type": "tuic",
        "server": "204.10.192.96",
        "server_port": 8445,
        "uuid": "11111111-2222-3333-4444-555555555555",
        "password": "tuic pass",
        "congestion_control": "cubic",
        "zero_rtt_handshake": True,
        "tls": {
            "enabled": True,
            "server_name": "204.10.192.96",
            "insecure": True,
        },
    }
}
tuic = standard_share_uri("tuic", tuic_item, "MV17-14-tr-tuic-6")
assert tuic.startswith("tuic://11111111-2222-3333-4444-555555555555:")
assert "allow_insecure=1" in tuic
assert karing_inline_uri("tuic", tuic_item, "MV17-14-tr-tuic-6").startswith(
    "karing://install-config?url="
)


anytls_item = {
    "outbound": {
        "type": "anytls",
        "server": "204.10.192.96",
        "server_port": 8446,
        "password": "anytls-pass",
        "tls": {
            "enabled": True,
            "server_name": "204.10.192.96",
            "insecure": True,
        },
    }
}
anytls = standard_share_uri("anytls", anytls_item, "MV17-14-tr-anytls-6")
assert anytls.startswith("anytls://anytls-pass@204.10.192.96:8446/")
assert "security=tls" in anytls
assert karing_inline_uri("anytls", anytls_item, "MV17-14-tr-anytls-6").startswith(
    "karing://install-config?url="
)


# Naive must preserve the full managed CA content. It intentionally does not
# use a lossy compact share URI.
naive_config = {
    "outbounds": [
        {
            "type": "naive",
            "tag": "twinpanel-naive",
            "server": "204.10.192.96",
            "server_port": 8447,
            "username": "tp-sub-17",
            "password": "naive-secret",
            "tls": {
                "enabled": True,
                "server_name": "204.10.192.96",
                "certificate": "-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----\n",
            },
        }
    ]
}
naive_item = {
    "config": json.dumps(naive_config),
    "config_format": "sing-box",
    "outbound": naive_config["outbounds"][0],
}
naive_content = copy_content("naive", naive_item, "MV17-14-tr-naive-6")
assert "BEGIN CERTIFICATE" in naive_content
naive_karing = karing_inline_uri("naive", naive_item, "MV17-14-tr-naive-6")
naive_params = parse_qs(urlsplit(naive_karing).query)
assert "BEGIN CERTIFICATE" in naive_params["url"][0]
assert standard_share_uri("naive", naive_item, "MV17-14-tr-naive-6") == ""


# Mieru gets its Karing-compatible YAML inline, not an HTTP profile URL.
mieru_item = {"config": '{"profiles":[]}', "config_format": "mieru-json"}
mieru_content = copy_content("mieru", mieru_item, "MV17-14-tr-mieru-6")
assert "MV17-14-tr-mieru-6" in mieru_content
mieru_karing = karing_inline_uri("mieru", mieru_item, "MV17-14-tr-mieru-6")
assert mieru_karing.startswith("karing://install-config?url=")
assert "http://" not in mieru_karing and "https://" not in mieru_karing


# Karing 1.2.25 must not be falsely advertised for protocols whose direct JSON
# import arrives in Karing 1.2.26+.
for protocol in ("snell", "sudoku", "trusttunnel"):
    assert karing_inline_uri(protocol, {"config": "{}"}, protocol) == ""


# Universal copy compatibility is injected for classic file actions and app
# launches, and uses an HTTP-safe execCommand fallback.
for marker in (
    "document.querySelectorAll('.download-config[data-target]')",
    "document.execCommand('copy')",
    "window.isSecureContext",
    "a.v13-open-uri[href]",
    "tp-v15-karing-classic",
):
    assert marker in v15, marker

print("PUBLIC_CONNECTION_MODERN_IMPORT_V15_SMOKE=PASS")
print("KARING_IMPORT=registered-karing-scheme-inline-content")
print("CLASSIC_COPY=openvpn-wireguard-hidden-source")
print("MODERN_COPY=all-ready-modern-items")
print("APP_FALLBACK=copy-before-launch")
print("NAIVE_TRUST=full-managed-ca-preserved")
