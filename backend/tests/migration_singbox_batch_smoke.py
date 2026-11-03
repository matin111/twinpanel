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
    values = {"json": json, "CONFIG_PATH": str(config), "STATE_PATH": str(state),
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
        batch(secrets * 5)
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
