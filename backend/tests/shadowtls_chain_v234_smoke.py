from __future__ import annotations

import ast
import contextlib
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PATH = ROOT / "backend" / "app" / "modern_protocol_runtime_v2.py"
ACCOUNT_PATH = ROOT / "backend" / "app" / "singbox_subscription_accounts.py"

runtime_source = RUNTIME_PATH.read_text(encoding="utf-8")
account_source = ACCOUNT_PATH.read_text(encoding="utf-8")
compile(runtime_source, str(RUNTIME_PATH), "exec")
compile(account_source, str(ACCOUNT_PATH), "exec")

runtime_tree = ast.parse(runtime_source, filename=str(RUNTIME_PATH))
account_tree = ast.parse(account_source, filename=str(ACCOUNT_PATH))


def function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def exec_functions(tree: ast.Module, names: tuple[str, ...], namespace: dict[str, Any]) -> None:
    nodes = [function_node(tree, name) for name in names]
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), "<smoke-functions>", "exec"),
        namespace,
    )


with tempfile.TemporaryDirectory(prefix="twinpanel-shadowtls-v234-") as temp_dir:
    root = Path(temp_dir)
    config_path = root / "config.json"
    state_path = root / "state.json"
    cert_path = str(root / "cert.pem")
    key_path = str(root / "key.pem")

    config_path.write_text(
        json.dumps({"inbounds": [], "outbounds": []}),
        encoding="utf-8",
    )
    state_path.write_text("{}\n", encoding="utf-8")

    runtime_ns: dict[str, Any] = {
        "json": json,
        "Any": Any,
        "CONFIG_PATH": str(config_path),
        "STATE_PATH": str(state_path),
        "CERT_PATH": cert_path,
        "KEY_PATH": key_path,
        "SHADOWTLS_INNER_TAG": "twinpanel-shadowtls-inner",
        "SHADOWTLS_INNER_METHOD": "aes-256-gcm",
    }
    exec_functions(runtime_tree, ("_mutation_script",), runtime_ns)

    desired = [
        {
            "protocol": "shadowtls",
            "tag": "twinpanel-shadowtls-in",
            "port": 8448,
            "settings": {
                "handshake_server": "www.microsoft.com",
                "handshake_port": 443,
                "strict_mode": True,
            },
        }
    ]
    generated_runtime = runtime_ns["_mutation_script"](desired)
    compile(generated_runtime, "generated-shadowtls-runtime.py", "exec")
    exec(generated_runtime, {})

    staged = json.loads(Path(str(config_path) + ".new").read_text(encoding="utf-8"))
    Path(str(config_path) + ".new").replace(config_path)
    outer = next(item for item in staged["inbounds"] if item.get("tag") == "twinpanel-shadowtls-in")
    inner = next(item for item in staged["inbounds"] if item.get("tag") == "twinpanel-shadowtls-inner")
    assert outer["type"] == "shadowtls"
    assert outer["detour"] == "twinpanel-shadowtls-inner"
    assert inner["type"] == "shadowsocks"
    assert inner["method"] == "aes-256-gcm"
    assert inner["listen"] == "127.0.0.1"
    assert inner["password"]
    assert inner["password"] != outer["users"][0]["password"]

    runtime_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert runtime_state["shadowtls"]["inner_password"] == inner["password"]

    account_ns: dict[str, Any] = {
        "json": json,
        "Any": Any,
        "Node": object,
        "SingBoxAccountSecret": object,
        "SingBoxAccountError": RuntimeError,
        "CONFIG_PATH": str(config_path),
        "STATE_PATH": str(state_path),
        "CERT_PATH": cert_path,
        "REVOCATION_SENTINEL": "__twinpanel_revoked__",
        "TAGS": {"shadowtls": "twinpanel-shadowtls-in"},
        "SHADOWTLS_INNER_TAG": "twinpanel-shadowtls-inner",
        "SHADOWTLS_INNER_METHOD": "aes-256-gcm",
    }
    exec_functions(
        account_tree,
        (
            "_mutation_script",
            "_snapshot_script",
            "_node_host",
            "_client_tls",
            "client_outbound",
            "client_item",
        ),
        account_ns,
    )

    subscriber_password = "subscription-shadowtls-password"
    record = {
        "name": "tp-sub-17",
        "password": subscriber_password,
    }
    generated_account = account_ns["_mutation_script"](
        "shadowtls",
        "tp-sub-17",
        record,
    )
    compile(generated_account, "generated-shadowtls-account.py", "exec")
    exec(generated_account, {})
    Path(str(config_path) + ".account-new").replace(config_path)

    healed = json.loads(config_path.read_text(encoding="utf-8"))
    outer = next(item for item in healed["inbounds"] if item.get("tag") == "twinpanel-shadowtls-in")
    inner = next(item for item in healed["inbounds"] if item.get("tag") == "twinpanel-shadowtls-inner")
    users = outer["users"]
    assert record in users
    assert any(item.get("name") == "twinpanel-bootstrap" for item in users)
    assert not any(str(item.get("name") or "").startswith("__twinpanel_revoked__") for item in users)
    assert outer["detour"] == "twinpanel-shadowtls-inner"
    assert inner["password"] != subscriber_password

    snapshot_script = account_ns["_snapshot_script"]("shadowtls")
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        exec(snapshot_script, {})
    snapshot = json.loads(capture.getvalue().strip().splitlines()[-1])
    assert snapshot["_twinpanel_shadowtls_inner"]["password"] == inner["password"]

    node = SimpleNamespace(
        id=5,
        name="usa",
        public_domain=None,
        public_ip="64.49.12.176",
    )
    secret = SimpleNamespace(
        protocol="shadowtls",
        username="tp-sub-17",
        password=subscriber_password,
        uuid=None,
        userkey=None,
    )
    item = account_ns["client_item"](node, secret, snapshot)
    client = json.loads(item["config"])
    assert len(client["outbounds"]) == 2
    proxy, transport = client["outbounds"]
    assert proxy["type"] == "shadowsocks"
    assert proxy["tag"] == "twinpanel-shadowtls"
    assert proxy["detour"] == "twinpanel-shadowtls-transport"
    assert proxy["method"] == "aes-256-gcm"
    assert proxy["password"] == inner["password"]
    assert proxy["password"] != subscriber_password
    assert transport["type"] == "shadowtls"
    assert transport["tag"] == "twinpanel-shadowtls-transport"
    assert transport["password"] == subscriber_password
    assert transport["server"] == "64.49.12.176"
    assert transport["server_port"] == 8448
    assert client["route"]["final"] == "twinpanel-shadowtls"
    assert item["server"] == "64.49.12.176"
    assert item["port"] == 8448
    assert item["outbound"]["type"] == "shadowtls"

    # Regression guard: a healthy non-ShadowTLS protocol remains a one-outbound
    # client payload with no detour chain introduced by this repair.
    hy_secret = SimpleNamespace(
        protocol="hysteria2",
        username="tp-sub-17",
        password="hy2-password",
        uuid=None,
        userkey=None,
    )
    hy_inbound = {
        "type": "hysteria2",
        "tag": "twinpanel-hysteria2-in",
        "listen_port": 8444,
        "tls": {"certificate_path": cert_path},
    }
    hy_item = account_ns["client_item"](node, hy_secret, hy_inbound)
    hy_config = json.loads(hy_item["config"])
    assert len(hy_config["outbounds"]) == 1
    assert hy_config["outbounds"][0]["type"] == "hysteria2"
    assert "detour" not in hy_config["outbounds"][0]

print("SHADOWTLS_CHAIN_V234_SMOKE=PASS")
print("SERVER_CHAIN=SHADOWTLS_TO_SHADOWSOCKS")
print("CLIENT_CHAIN=SHADOWSOCKS_TO_SHADOWTLS")
print("SUBSCRIPTION_CREDENTIAL_ROTATION=NO")
print("HYSTERIA2_REGRESSION=PASS")
