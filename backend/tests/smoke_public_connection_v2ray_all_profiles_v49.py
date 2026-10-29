from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "backend/app/routers/public_connection_multilink_v7.py"
ACTION_TARGET = ROOT / "backend/app/routers/public_connection_v2ray_multilink_action_v44.py"
source = TARGET.read_text(encoding="utf-8")
action_source = ACTION_TARGET.read_text(encoding="utf-8")
module_ast = ast.parse(source)


def function_node(name: str) -> ast.FunctionDef:
    for node in module_ast.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing function: {name}")


# Execute the real helper in isolation so this smoke test does not need a live
# database/FastAPI app. The delivery selector is stubbed with the exact ordered
# profiles each item exposes to customers.
def customer_profiles(item: dict[str, Any]) -> list[dict[str, Any]]:
    return list(item.get("profiles") or [])


namespace: dict[str, Any] = {
    "Any": Any,
    "xray_delivery": SimpleNamespace(_customer_profiles=customer_profiles),
}
helper_ast = ast.Module(body=[function_node("_item_v2ray_uris")], type_ignores=[])
ast.fix_missing_locations(helper_ast)
exec(compile(helper_ast, str(TARGET), "exec"), namespace)
item_v2ray_uris = namespace["_item_v2ray_uris"]


def profiles(server: str) -> list[dict[str, str]]:
    return [
        {
            "id": "xhttp_reality",
            "title": "XHTTP Reality",
            "transport": "xhttp",
            "security": "reality",
            "uri": f"vless://uuid@{server}:24001?type=xhttp#{server}-XHTTP",
        },
        {
            "id": "grpc_reality",
            "title": "gRPC Reality",
            "transport": "grpc",
            "security": "reality",
            "uri": f"vless://uuid@{server}:25001?type=grpc#{server}-gRPC",
        },
        {
            "id": "tcp_reality",
            "title": "TCP Reality",
            "transport": "tcp",
            "security": "reality",
            "uri": f"vless://uuid@{server}:38001?type=tcp#{server}-TCP",
        },
    ]


server_a = {"node_id": 10, "uri": "vless://legacy-a", "profiles": profiles("a.example")}
server_b = {"node_id": 20, "uri": "vless://legacy-b", "profiles": profiles("b.example")}

# Regression contract: one server with three real profiles must yield all three,
# never only item.uri. Two servers therefore contribute six distinct URIs.
a = item_v2ray_uris(server_a)
b = item_v2ray_uris(server_b)
assert len(a) == 3, a
assert len(b) == 3, b
assert len(a + b) == 6
assert a == [profile["uri"] for profile in server_a["profiles"]]
assert b == [profile["uri"] for profile in server_b["profiles"]]
assert server_a["uri"] not in a
assert server_b["uri"] not in b

# Exact duplicate profile URIs are deduplicated inside a server without changing
# producer-provided order.
duplicate = dict(server_a)
duplicate["profiles"] = server_a["profiles"] + [dict(server_a["profiles"][1])]
assert item_v2ray_uris(duplicate) == a

# True legacy credentials without a usable profiles[] collection keep the old
# single-URI compatibility behavior.
legacy = {"uri": "vless://uuid@legacy.example:443?type=tcp#Legacy"}
assert item_v2ray_uris(legacy) == [legacy["uri"]]
assert item_v2ray_uris({}) == []

# Architecture guardrails: grouped metadata remains available and the neutral
# canonical subscription route reuses the same payload without protocol words in
# the public URL. Historical routes remain for compatibility only.
assert "def _v2ray_profile_groups" in source
assert '"/{token}/subscription/v2ray/meta"' in source
assert '"/{token}/sub"' in source
assert '"/{token}/sub/meta"' in source
assert 'name="public_v2ray_subscription_neutral_v50"' in source
assert 'request.url_for("public_v2ray_subscription_neutral_v50"' in source
assert '"X-TwinPanel-Server-Count"' in source
assert '"X-TwinPanel-Profile-Count"' in source
assert "xray_delivery._customer_profiles(item)" in source

# Public Connect/Hiddify must use the neutral path so plaintext-path DPI never
# sees the protocol product name. Per-profile direct Hiddify URIs stay unchanged.
assert "'/sub'" in action_source
assert "'/sub/meta'" in action_source
assert "card.dataset.v44Endpoint='/sub'" in action_source
assert "+'/multi/v2ray'" not in action_source
assert "+'/subscription/v2ray/meta'" not in action_source

print("Public Connect V2Ray all-profiles V49/V50 smoke: PASS")
