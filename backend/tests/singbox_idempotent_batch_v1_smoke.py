"""NOVA-inspired, original implementation: no-op sing-box batch contracts.

This is dependency-free and executes the exact embedded remote Python mutation
script on temporary configs, never against a live server.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "backend/app/singbox_subscription_accounts.py"
text = SOURCE.read_text(encoding="utf-8")
compile(text, str(SOURCE), "exec")
tree = ast.parse(text)
nodes = [
    node for node in tree.body
    if isinstance(node, ast.FunctionDef)
    and node.name in {"_batch_mutation_script", "_mutation_script", "_user_record"}
]
assert len(nodes) == 3


@dataclass
class Secret:
    protocol: str
    username: str
    password: str
    uuid: str | None = None
    userkey: str | None = None


protocols = ("hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell")
tags = {p: "twinpanel-" + p + "-in" for p in protocols}


def generate(path: Path, state: Path):
    ns = {
        "json": json, "CONFIG_PATH": str(path), "STATE_PATH": str(state),
        "SINGBOX_PROTOCOLS": set(protocols), "TAGS": tags,
        "REVOCATION_SENTINEL": "__twinpanel_revoked__",
        "SHADOWTLS_INNER_TAG": "twinpanel-shadowtls-inner",
        "SHADOWTLS_INNER_METHOD": "aes-256-gcm",
        "SingBoxAccountError": RuntimeError, "SingBoxAccountSecret": Secret,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


def execute(script: str) -> str:
    compile(script, "generated-singbox-idempotent.py", "exec")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            exec(script, {})
        except SystemExit as exc:
            assert exc.code in (0, None), exc
    return output.getvalue().strip()


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    cfg = root / "config.json"
    state = root / "state.json"
    config = {"inbounds": [
        {"type": p, "tag": tags[p], "users": [
            {"username" if p == "naive" else "name": "unrelated-1", "password": "keep"},
            {"username" if p == "naive" else "name": "unrelated-2", "password": "keep"},
        ]} for p in protocols
    ]}
    cfg.write_text(json.dumps(config), encoding="utf-8")
    batch = generate(cfg, state)["_batch_mutation_script"]
    secrets = [
        Secret(p, "tp-sub-51", "secret-51",
               uuid="11111111-2222-3333-4444-555555555555",
               userkey="userkey-51")
        for p in protocols
    ]

    # New batch stages a change.
    out = execute(batch(secrets))
    assert "batch_users=6" in out
    staged_cfg = Path(str(cfg) + ".account-new")
    staged_state = Path(str(state) + ".account-new")
    assert staged_cfg.exists()
    staged_cfg.replace(cfg)
    assert staged_state.exists()
    staged_state.replace(state)
    snapshot = cfg.read_bytes()
    original_inbounds = json.loads(snapshot)["inbounds"]
    assert original_inbounds[0]["users"][0]["name"] == "unrelated-1"

    # Repeated sync must not write any staging file; no-op marker is consumed
    # by the shell to avoid validating and restarting an unchanged node.
    out = execute(batch(secrets))
    assert out == "batch_unchanged=1", out
    assert not staged_cfg.exists()
    assert not staged_state.exists()
    assert cfg.read_bytes() == snapshot

    # Add a stale revoked user marker; the next batch must clean it even when
    # the requested real user is otherwise identical.
    config = json.loads(cfg.read_text())
    config["inbounds"][0]["users"].append({
        "name": "__twinpanel_revoked__dead", "password": "invalid",
    })
    cfg.write_text(json.dumps(config), encoding="utf-8")
    out = execute(batch(secrets))
    assert "batch_users=6" in out
    changed = json.loads(staged_cfg.read_text())
    assert not any(
        u.get("name", "").startswith("__twinpanel_revoked__")
        for u in changed["inbounds"][0]["users"]
    )
    staged_cfg.replace(cfg)
    if staged_state.exists():
        staged_state.replace(state)

    # Changing one secret should stage a real update without touching the
    # unrelated client on the same inbound or any other protocol.
    updated = list(secrets)
    updated[0] = replace(updated[0], password="secret-52")
    out = execute(batch(updated))
    assert "batch_users=6" in out
    changed = json.loads(staged_cfg.read_text())
    inbound = changed["inbounds"][0]
    assert inbound["users"][0]["name"] == "unrelated-1"
    assert next(u for u in inbound["users"] if u["name"] == "tp-sub-51")["password"] == "secret-52"
    assert changed["inbounds"][1]["users"] == json.loads(cfg.read_text())["inbounds"][1]["users"]

# The existing single-account provisioner also must skip an identical
# reapply, including ShadowTLS's private inner runtime state.
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    cfg = root / "single.json"
    state = root / "single-state.json"
    gen = generate(cfg, state)["_mutation_script"]
    for protocol in protocols:
        cfg.write_text(json.dumps({"inbounds": [{
            "type": protocol, "tag": tags[protocol], "users": [
                {"username" if protocol == "naive" else "name": "unrelated", "password": "keep"},
            ],
        }]}), encoding="utf-8")
        record = (
            {"username": "tp-sub-52", "password": "password"}
            if protocol == "naive" else
            {"name": "tp-sub-52", "uuid": "11111111-2222-3333-4444-555555555555", "password": "password"}
            if protocol == "tuic" else
            {"name": "tp-sub-52", "userkey": "key"}
            if protocol == "snell" else
            {"name": "tp-sub-52", "password": "password"}
        )
        out = execute(gen(protocol, "tp-sub-52", record))
        assert "account_users=2" in out, (protocol, out)
        staged = Path(str(cfg) + ".account-new")
        assert staged.exists(), protocol
        staged.replace(cfg)
        snapshot = cfg.read_bytes()
        out = execute(gen(protocol, "tp-sub-52", record))
        assert out == "account_unchanged=1", (protocol, out)
        assert not staged.exists(), protocol
        assert cfg.read_bytes() == snapshot, protocol
        # Existing user identities and server-side bootstrap remain intact.
        data = json.loads(snapshot)
        inbound = next(i for i in data["inbounds"] if i.get("tag") == tags[protocol])
        assert inbound["users"][0].get("name", inbound["users"][0].get("username")) == "unrelated"

# Shell contract: only changed batches validate, write, and restart. On an
# unchanged batch, an inactive service is still started (self-healing).
assert 'batch_unchanged=1' in text
assert 'account_unchanged=1' in text
assert r'\"$result\"' in text and "'batch_unchanged=1'" in text
assert 'systemctl is-active --quiet {SERVICE_NAME}.service || systemctl restart' in text
assert 'flock -x 9' in text
print("SINGBOX_IDEMPOTENT_BATCH_V1=PASS")
