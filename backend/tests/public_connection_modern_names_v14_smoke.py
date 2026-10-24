from __future__ import annotations

import ast
import re
import secrets
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
ROUTERS = ROOT / "backend" / "app" / "routers"

v14_path = ROUTERS / "public_connection_modern_names_v14.py"
live_path = ROUTERS / "public_connection_hub_live_v5.py"

v14 = v14_path.read_text(encoding="utf-8")
live = live_path.read_text(encoding="utf-8")

compile(v14, str(v14_path), "exec")
compile(live, str(live_path), "exec")

for marker in (
    '"/{token}/modern-config-v14/{protocol}/{node_id}"',
    "def _account_name(",
    "def _node_name(",
    "def _profile_name(",
    "def _download_stem(",
    'getattr(sub, "account_username", None)',
    'item.get("node")',
    "secrets.token_hex(2)",
    "Content-Disposition",
    "data-config-name",
    "button.dataset.configName||'user'",
    "def _named_sudoku_uri(",
    "def _named_mieru_karing_yaml(",
):
    assert marker in v14, marker

# V14 is additive and must run after the already accepted V13 delivery layer.
for marker in (
    "public_connection_modern_names_v14_router",
    "router.include_router(public_connection_modern_names_v14_router)",
    "refine_public_connection_modern_names_v14(source, token, db)",
):
    assert marker in live, marker
assert live.index("refine_public_connection_modern_delivery_v13(source, token, db)") < live.index(
    "refine_public_connection_modern_names_v14(source, token, db)"
)

# Execute only the pure naming helpers without importing FastAPI/application
# dependencies. This locks the customer-visible naming contract.
tree = ast.parse(v14)
helper_names = {
    "_safe_component",
    "_account_name",
    "_node_name",
    "_profile_name",
    "_download_stem",
}
helper_nodes = [
    node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    and node.name in helper_names
]
module = ast.Module(body=helper_nodes, type_ignores=[])
ast.fix_missing_locations(module)
namespace: dict[str, Any] = {
    "Any": Any,
    "re": re,
    "secrets": secrets,
    "_ALLOWED_COMPONENT": re.compile(r"[^A-Za-z0-9_=+.-]+"),
}
exec(compile(module, str(v14_path), "exec"), namespace)

sub = SimpleNamespace(id=17, account_username="MV17-14")
usa = {"node_id": 5, "node": "usa"}
tr = {"node_id": 6, "node": "tr"}

profile_name = namespace["_profile_name"]
download_stem = namespace["_download_stem"]
account_name = namespace["_account_name"]

assert account_name(sub) == "MV17-14"
assert profile_name(sub, "tuic", usa) == "MV17-14-usa-tuic-5"
assert profile_name(sub, "hysteria2", tr) == "MV17-14-tr-hysteria2-6"
assert download_stem(sub, "tuic", usa) == "MV17-14-usa-tuic-5"
assert download_stem(sub, "mieru", tr) == "MV17-14-tr-mieru-6"

# AmneziaWG Windows tunnel names must match upstream WireGuard's exact
# [A-Za-z0-9_=+.-]{1,32} contract. Repeated downloads must also receive unique
# safe names so Chrome never needs to append the invalid " (1)" suffix.
awg_names = {download_stem(sub, "amneziawg", usa) for _ in range(16)}
assert len(awg_names) == 16
for name in awg_names:
    assert name.startswith("MV17-14-usa-amneziawg-")
    assert 1 <= len(name) <= 32
    assert re.fullmatch(r"[A-Za-z0-9_=+.-]+", name)
    assert " " not in name
    assert "(" not in name and ")" not in name

# Unsafe display values are sanitized, but username remains the first component.
unsafe_sub = SimpleNamespace(id=99, account_username="Ali User/01")
unsafe_item = {"node_id": 12, "node": "United States / West"}
unsafe_name = profile_name(unsafe_sub, "snell", unsafe_item)
assert unsafe_name.startswith("Ali-User-01-")
assert "/" not in unsafe_name and " " not in unsafe_name

# The route returns the original config bytes; V14 changes only customer-facing
# filename/profile metadata, never credentials or protocol payloads.
assert "content = config" in v14
assert "secret_encrypted" not in v14
assert "config_text_encrypted" not in v14

print("PUBLIC_CONNECTION_MODERN_NAMES_V14_SMOKE=PASS")
print("NAMING=username-country-protocol-node")
print("EXAMPLE=MV17-14-usa-tuic-5.json")
print("AMNEZIAWG=windows-safe-unique-under-32")
print("RUNTIME_PAYLOAD=UNCHANGED")
