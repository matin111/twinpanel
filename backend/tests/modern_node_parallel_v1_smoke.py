from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app" / "modern_node_parallel_v1.py"
CENTRAL = ROOT / "app" / "routers" / "central_account_delivery_runtime_v3.py"
MODERN = ROOT / "app" / "routers" / "modern_account_delivery_v1.py"


source = MODULE.read_text(encoding="utf-8")
central = CENTRAL.read_text(encoding="utf-8")
modern = MODERN.read_text(encoding="utf-8")
tree = ast.parse(source)

limit = None
for node in tree.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "MAX_PARALLEL_MODERN_NODES":
                limit = ast.literal_eval(node.value)
assert limit == 3, limit
assert "asyncio.Semaphore(MAX_PARALLEL_MODERN_NODES)" in source
assert "asyncio.gather(*(provision_target(target) for target in targets))" in source

remote_work = None
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "remote_work":
        remote_work = node
        break
assert remote_work is not None
remote_names = {
    node.id
    for node in ast.walk(remote_work)
    if isinstance(node, ast.Name)
}
assert "db" not in remote_names, remote_names

assert "if standalone and secret is None:" in source
assert source.index("if standalone and secret is None:") < source.index("asyncio.Semaphore")

assert "install_bounded_modern_node_provisioning_v1()" in central
assert "modern._provision_modern_protocol = _provision_modern_protocol_parallel" in source

assert "for protocol in protocols:" in modern
assert "_provision_classic_protocol(" in modern

print("modern_node_parallel_v1_smoke: OK")
