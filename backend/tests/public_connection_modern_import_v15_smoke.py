from __future__ import annotations

import ast
import base64
import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit


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
    "ulink://install/?content=",
    "&format=json#",
    '"hysteria2"',
    '"tuic"',
    '"anytls"',
    '"naive"',
    '"shadowtls"',
    "def karing_inline_uri(",
    "def standard_share_uri(",
    "v15-karing-inline",
    "کپی لینک استاندارد",
):
    assert marker in v15, marker

# V15 is additive and must refine V14's named download paths, not replace the
# already accepted V13/V14 delivery layers.
assert "refine_public_connection_modern_import_v15" in live
assert live.index("refine_public_connection_modern_names_v14(source, token, db)") < live.index(
    "refine_public_connection_modern_import_v15(source, token, db)"
)

# Execute only pure link helpers without importing the application stack.
tree = ast.parse(v15)
helper_names = {
    "_host_for_uri",
    "_outbound",
    "karing_inline_uri",
    "_tls_params",
    "standard_share_uri",
}
helper_nodes = [
    node
    for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name in helper_names
]
module = ast.Module(body=helper_nodes, type_ignores=[])
ast.fix_missing_locations(module)
namespace: dict[str, Any] = {
    "Any": Any,
    "base64": base64,
    "copy": copy,
    "json": json,
    "quote": quote,
    "urlencode": urlencode,
    "KARING_INLINE_PROTOCOLS": {
        "hysteria2",
        "tuic",
        "anytls",
        "naive",
        "shadowtls",
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

karing = karing_inline_uri(
    "hysteria2",
    hysteria_item,
    "MV17-14-tr-hysteria2-6",
)
assert karing.startswith("ulink://install/?content=")
assert "http://" not in karing and "https://" not in karing
parts = urlsplit(karing)
params = parse_qs(parts.query)
assert params.get("format") == ["json"]
raw = base64.b64decode(params["content"][0]).decode("utf-8")
nodes = json.loads(raw)
assert isinstance(nodes, list) and len(nodes) == 1
assert nodes[0]["type"] == "hysteria2"
assert nodes[0]["tag"] == "MV17-14-tr-hysteria2-6"
assert nodes[0]["password"] == "hy2 pass+/="
assert nodes[0]["tls"]["insecure"] is True

hysteria_link = standard_share_uri(
    "hysteria2",
    hysteria_item,
    "MV17-14-tr-hysteria2-6",
)
assert hysteria_link.startswith("hysteria2://")
assert "insecure=1" in hysteria_link
assert "obfs=salamander" in hysteria_link
assert "obfs-password=obfs+secret" in hysteria_link


tuic_item = {
    "outbound": {
        "type": "tuic",
        "tag": "twinpanel-tuic",
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
tuic_link = standard_share_uri("tuic", tuic_item, "MV17-14-tr-tuic-6")
assert tuic_link.startswith("tuic://11111111-2222-3333-4444-555555555555:")
assert "congestion_control=cubic" in tuic_link
assert "udp_relay_mode=native" in tuic_link
assert "allow_insecure=1" in tuic_link
assert "reduce_rtt=1" in tuic_link


anytls_item = {
    "outbound": {
        "type": "anytls",
        "tag": "twinpanel-anytls",
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
anytls_link = standard_share_uri(
    "anytls",
    anytls_item,
    "MV17-14-tr-anytls-6",
)
assert anytls_link.startswith("anytls://anytls-pass@204.10.192.96:8446/")
assert "security=tls" in anytls_link
assert "sni=204.10.192.96" in anytls_link
assert "insecure=1" in anytls_link


# Naive must keep the complete TLS certificate inside Karing's embedded JSON.
# A compact share URI is deliberately not emitted because the managed CA trust
# material cannot be represented safely by the common naive+https URI subset.
naive_item = {
    "outbound": {
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
}
naive_ulink = karing_inline_uri("naive", naive_item, "MV17-14-tr-naive-6")
naive_params = parse_qs(urlsplit(naive_ulink).query)
naive_nodes = json.loads(base64.b64decode(naive_params["content"][0]).decode("utf-8"))
assert "BEGIN CERTIFICATE" in naive_nodes[0]["tls"]["certificate"]
assert standard_share_uri("naive", naive_item, "MV17-14-tr-naive-6") == ""

# Unsupported Karing-inline protocols continue using their existing native/file
# delivery instead of being falsely advertised as one-click Karing imports.
snell_item = {
    "outbound": {
        "type": "snell",
        "server": "204.10.192.96",
        "server_port": 8448,
    }
}
assert karing_inline_uri("snell", snell_item, "snell") == ""

print("PUBLIC_CONNECTION_MODERN_IMPORT_V15_SMOKE=PASS")
print("KARING_IMPORT=embedded-ulink-no-remote-fetch")
print("STANDARD_LINKS=hysteria2,tuic,anytls")
print("NAIVE_TRUST=embedded-ca-preserved")
