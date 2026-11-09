from __future__ import annotations
import ast
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "backend/app/singbox_subscription_accounts.py"
WORKER_PATH = ROOT / "backend/scripts/twinpanel_migration_singbox_batch.py"
source = SOURCE_PATH.read_text(encoding="utf-8")
worker = WORKER_PATH.read_text(encoding="utf-8")
compile(source, str(SOURCE_PATH), "exec")
compile(worker, str(WORKER_PATH), "exec")
tree = ast.parse(source)
names = ("_batch_mutation_script", "_user_record")
nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(nodes) == len(names)

@dataclass
class Secret:
    protocol: str
    username: str
    password: str
    uuid: str | None = None
    userkey: str | None = None

protocols = ("hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell")
with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    config = base / "config.json"
    state = base / "state.json"
    config.write_text(json.dumps({"inbounds": [
        {"type": p, "tag": "tp-" + p, "users": [
            {"username" if p == "naive" else "name": "old-live-user", "password": "keep"}
        ]} for p in protocols]}), encoding="utf-8")
    values = {"parallel_user_sync_script": __import__("app.services.shadowtls_2022_identity_v1",fromlist=["parallel_user_sync_script"]).parallel_user_sync_script,
              "json": json, "CONFIG_PATH": str(config), "STATE_PATH": str(state),
              "SINGBOX_PROTOCOLS": set(protocols),
              "TAGS": {p: "tp-"+p for p in protocols},
              "REVOCATION_SENTINEL": "__twinpanel_revoked__",
              "SHADOWTLS_INNER_TAG": "twinpanel-shadowtls-inner",
              "SHADOWTLS_INNER_METHOD": "aes-256-gcm",
              "SingBoxAccountError": RuntimeError,
              "SingBoxAccountSecret": Secret}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE_PATH), "exec"), values)
    batch = values["_batch_mutation_script"]
    secrets = []
    for p in protocols:
        secrets.append(Secret(p, "tp-sub-1", "password-1",
                              uuid="11111111-2222-3333-4444-555555555555",
                              userkey="userkey-1"))
        secrets.append(Secret(p, "tp-sub-2", "password-2",
                              uuid="22222222-3333-4444-5555-666666666666",
                              userkey="userkey-2"))
    generated = batch(secrets)
    compile(generated, "generated-singbox-batch.py", "exec")
    exec(generated, {})
    staged = json.loads(Path(str(config)+".account-new").read_text())
    for p in protocols:
        inbound = next(r for r in staged["inbounds"] if r.get("type") == p)
        key = "username" if p == "naive" else "name"
        assert {r[key] for r in inbound["users"]} == {
            "old-live-user", "tp-sub-1", "tp-sub-2"
        }
    inner = next(r for r in staged["inbounds"] if r.get("tag") == "twinpanel-shadowtls-inner")
    assert inner["type"] == "shadowsocks"
    assert inner["password"]
    assert json.loads(Path(str(state)+".account-new").read_text())["shadowtls"]["inner_password"] == inner["password"]
    try:
        batch(secrets * 13)
    except RuntimeError:
        pass
    else:
        raise AssertionError("oversized batch was accepted")

assert "systemctl restart" in source
assert "flock -x 9" in source
assert "SOURCES = (" in worker and "MigrationImportRecord.source.in_(SOURCES)" in worker
assert "SubscriptionNode.node_id == node.id" in worker
assert "if any(" in worker and "ad._autosync_item_node_id" in worker
print("MIGRATION_SINGBOX_BATCH_SMOKE=PASS")

CONVERGENCE_PATH = ROOT / "backend/app/node_subscription_convergence_v114.py"
convergence = CONVERGENCE_PATH.read_text(encoding="utf-8")
compile(convergence, str(CONVERGENCE_PATH), "exec")
# The convergence worker was redesigned after the original batch migration
# smoke: imported accounts now require explicit manual provisioning across all
# Modern protocols, not only sing-box accounts while the importer holds a lock.
# Assert the actual AST guard so a formatting change cannot silently bypass it.
convergence_tree = ast.parse(convergence, filename=str(CONVERGENCE_PATH))
modern_sync = next(
    item for item in convergence_tree.body
    if isinstance(item, ast.AsyncFunctionDef) and item.name == "_sync_modern_node"
)
protocol_loops = [
    item for item in ast.walk(modern_sync)
    if isinstance(item, ast.For)
    and isinstance(item.target, ast.Name) and item.target.id == "protocol"
    and isinstance(item.iter, ast.Name) and item.iter.id == "wanted"
]
assert len(protocol_loops) == 1, "missing Modern protocol provisioning loop"
skip_imported = [
    item for item in protocol_loops[0].body
    if isinstance(item, ast.If)
    and isinstance(item.test, ast.Compare)
    and len(item.test.ops) == 1
    and isinstance(item.test.ops[0], ast.In)
    and any(isinstance(comparator, ast.Name) and comparator.id == "imported_ids"
            for comparator in item.test.comparators)
    and any(isinstance(stmt, ast.Continue) for stmt in item.body)
]
assert skip_imported, "imported accounts must be skipped before provisioning"
modern_source = ast.get_source_segment(convergence, modern_sync) or ""
assert "MigrationImportRecord.subscription_id" in modern_source, (
    "Modern auto-convergence must identify imported subscriptions"
)

bounded_sync = next(
    item for item in convergence_tree.body
    if isinstance(item, ast.AsyncFunctionDef)
    and item.name == "_reconcile_bounded_exit_nodes_once"
)
bounded_source = ast.get_source_segment(convergence, bounded_sync) or ""
assert "MigrationImportRecord.subscription_id" in bounded_source, (
    "bounded convergence must identify imported subscriptions"
)
assert any(
    isinstance(item, ast.UnaryOp) and isinstance(item.op, ast.Invert)
    and isinstance(item.operand, ast.Call)
    and isinstance(item.operand.func, ast.Attribute)
    and item.operand.func.attr == "in_"
    and ast.unparse(item.operand.func.value) == "Subscription.id"
    and any(isinstance(arg, ast.Name) and arg.id == "imported"
            for arg in item.operand.args)
    for item in ast.walk(bounded_sync)
), "imported subscriptions must be excluded from bounded auto-convergence"

assert "_migration_singbox_worker_running()" in convergence
print("MIGRATION_MANUAL_PROVISION_EXCLUSION=PASS")
