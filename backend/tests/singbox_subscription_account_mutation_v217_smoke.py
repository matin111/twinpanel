from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "backend" / "app" / "singbox_subscription_accounts.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
compile(SOURCE, str(SOURCE_PATH), "exec")

tree = ast.parse(SOURCE, filename=str(SOURCE_PATH))
mutation_node = next(
    node
    for node in tree.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    and node.name == "_mutation_script"
)

protocols = (
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
)
tags = {protocol: f"tp-{protocol}" for protocol in protocols}

namespace = {
    "json": json,
    "TAGS": tags,
    "CONFIG_PATH": "",
    "STATE_PATH": "",
    "REVOCATION_SENTINEL": "__twinpanel_revoked__",
    "SHADOWTLS_INNER_TAG": "twinpanel-shadowtls-inner",
    "SHADOWTLS_INNER_METHOD": "aes-256-gcm",
}
exec(
    compile(
        ast.Module(body=[mutation_node], type_ignores=[]),
        str(SOURCE_PATH),
        "exec",
    ),
    namespace,
)
mutation_script = namespace["_mutation_script"]


def real_record(protocol: str) -> dict[str, str]:
    if protocol == "tuic":
        return {
            "name": "tp-sub-17",
            "uuid": "11111111-2222-3333-4444-555555555555",
            "password": "tuic-password",
        }
    if protocol == "naive":
        return {
            "username": "tp-sub-17",
            "password": "naive-password",
        }
    if protocol == "snell":
        return {
            "name": "tp-sub-17",
            "userkey": "snell-user-key",
        }
    return {
        "name": "tp-sub-17",
        "password": f"{protocol}-password",
    }


with tempfile.TemporaryDirectory(prefix="twinpanel-singbox-account-") as temp_dir:
    root = Path(temp_dir)

    for protocol in protocols:
        config_path = root / f"{protocol}.json"
        state_path = root / f"{protocol}-state.json"
        namespace["CONFIG_PATH"] = str(config_path)
        namespace["STATE_PATH"] = str(state_path)
        config_path.write_text(
            json.dumps(
                {
                    "inbounds": [
                        {
                            "type": protocol,
                            "tag": tags[protocol],
                            "listen_port": 20000,
                            "users": [],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        # Revoke with no remaining real users must generate one undisclosed
        # sentinel identity instead of leaving a shared inbound unauthenticated.
        revoke_script = mutation_script(protocol, "tp-sub-17", None)
        compile(revoke_script, f"generated-{protocol}-revoke.py", "exec")
        exec(revoke_script, {})

        staged_path = Path(str(config_path) + ".account-new")
        staged = json.loads(staged_path.read_text(encoding="utf-8"))
        users = staged["inbounds"][0]["users"]
        assert len(users) == 1, protocol
        key = "username" if protocol == "naive" else "name"
        assert users[0][key] == "__twinpanel_revoked__", protocol

        if protocol == "shadowtls":
            outer = staged["inbounds"][0]
            inner = next(
                item
                for item in staged["inbounds"]
                if item.get("tag") == "twinpanel-shadowtls-inner"
            )
            assert outer["detour"] == "twinpanel-shadowtls-inner"
            assert inner["type"] == "shadowsocks"
            assert inner["method"] == "aes-256-gcm"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            assert state["shadowtls"]["inner_password"] == inner["password"]

        # Emulate the real commit step and then provision the subscriber again.
        staged_path.replace(config_path)
        record = real_record(protocol)
        add_script = mutation_script(protocol, "tp-sub-17", record)
        compile(add_script, f"generated-{protocol}-add.py", "exec")
        exec(add_script, {})

        staged = json.loads(staged_path.read_text(encoding="utf-8"))
        users = staged["inbounds"][0]["users"]
        assert users == [record], protocol

print("SINGBOX_SUBSCRIPTION_ACCOUNT_MUTATION_V217_SMOKE=PASS")
print("PROTOCOLS=" + ",".join(protocols))
print("REVOCATION_SENTINEL=AUTHENTICATED")
print("REAL_ACCOUNT_RESTORE=PASS")
print("SHADOWTLS_CHAIN_STATE=PASS")
