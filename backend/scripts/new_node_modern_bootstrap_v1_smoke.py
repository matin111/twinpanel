from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
worker = (ROOT / "backend/app/routers/publish_node_all_users_v1.py").read_text(encoding="utf-8")
helper = (ROOT / "backend/app/services/new_node_modern_bootstrap_v1.py").read_text(encoding="utf-8")
registry = (ROOT / "backend/app/protocol_account_registry.py").read_text(encoding="utf-8")

bootstrap_call = "bootstrap_new_exit_modern_protocols("
publish_call = "result = await publish_node_to_all_users(node_id=node_id, db=db)"
assert bootstrap_call in worker, "Add Server worker no longer bootstraps Modern runtimes"
assert publish_call in worker, "Add Server worker no longer runs Publish-All"
assert worker.index(bootstrap_call) < worker.index(publish_call), "Modern bootstrap must happen before Publish-All"

assert "from ..routers.modern_protocol_admin_v3 import (" in helper
assert "result = await install(node_id=int(node_id), payload=payload, db=db)" in helper
assert "NodeProtocolConfig.status == \"online\"" in helper
assert "ModernProtocolSetting" in helper
assert "PROTOCOL_CATALOG" in helper
assert "Node.id != int(target.id)" in helper

modern = (
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
)
for protocol in modern:
    assert f'"{protocol}"' in registry, f"missing Modern registry protocol: {protocol}"

print("NEW_NODE_MODERN_BOOTSTRAP_V1_SMOKE=OK")
