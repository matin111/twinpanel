from __future__ import annotations

import textwrap
from pathlib import Path


SINGBOX_PATH = Path("backend/app/singbox_subscription_accounts.py")
STANDALONE_PATH = Path("backend/app/standalone_subscription_accounts.py")
SMOKE_PATH = Path("backend/tests/modern_real_runtime_provisioning_v2_smoke.py")
SMOKE_WORKFLOW_PATH = Path(".github/workflows/modern-real-runtime-provisioning-v2-smoke.yml")
ONE_SHOT_WORKFLOW_PATH = Path(".github/workflows/one-shot-modern-real-runtime-fix-v2.yml")
SELF_PATH = Path("scripts/one_shot_modern_runtime_fix_v2.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_singbox() -> None:
    text = SINGBOX_PATH.read_text(encoding="utf-8")
    old = '''    if PROTOCOL == "tuic":
        users = [{
            "name": SENTINEL,
            "uuid": str(uuid.uuid4()),
            "password": sentinel_password,
        }]
    elif PROTOCOL == "naive":
        users = [{
            "username": SENTINEL,
            "password": sentinel_password,
        }]
    elif PROTOCOL == "snell":
        users = [{
            "name": SENTINEL,
            "userkey": secrets.token_urlsafe(48),
        }]
    else:
        users = [{
            "name": SENTINEL,
            "password": sentinel_password,
        }]
'''
    new = '''    if PROTOCOL == "tuic":
        users = [dict(
            name=SENTINEL,
            uuid=str(uuid.uuid4()),
            password=sentinel_password,
        )]
    elif PROTOCOL == "naive":
        users = [dict(
            username=SENTINEL,
            password=sentinel_password,
        )]
    elif PROTOCOL == "snell":
        users = [dict(
            name=SENTINEL,
            userkey=secrets.token_urlsafe(48),
        )]
    else:
        users = [dict(
            name=SENTINEL,
            password=sentinel_password,
        )]
'''
    text = replace_once(text, old, new, "sing-box sentinel block")
    SINGBOX_PATH.write_text(text, encoding="utf-8")


def patch_amneziawg() -> None:
    text = STANDALONE_PATH.read_text(encoding="utf-8")
    anchor = '''async def _run_python(conn, script: str, *, timeout: int = 90) -> str:
    encoded = _encode_script(script)
    return await cmd(
        conn,
        f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3",
        timeout=timeout,
    )


'''
    helper = anchor + '''def _is_awg_key(value: str | None) -> bool:
    key = str(value or "").strip()
    if not key:
        return False
    try:
        return len(base64.b64decode(key, validate=True)) == 32
    except Exception:
        return False


def _extract_awg_private_key(config_text: str) -> str:
    for line in str(config_text or "").splitlines():
        left, separator, right = line.partition("=")
        if separator and left.strip() == "PrivateKey":
            key = right.strip()
            if not _is_awg_key(key):
                raise StandaloneAccountError("AmneziaWG server private key is invalid")
            return key
    raise StandaloneAccountError("AmneziaWG server private key unavailable")


'''
    text = replace_once(text, anchor, helper, "AmneziaWG helper anchor")

    old_validation = '''    if not private or not public:
        raise StandaloneAccountError("AmneziaWG client key generation returned empty key")
'''
    new_validation = '''    if not _is_awg_key(private) or not _is_awg_key(public):
        raise StandaloneAccountError("AmneziaWG client key generation returned invalid key")
'''
    text = replace_once(
        text,
        old_validation,
        new_validation,
        "AmneziaWG generated key validation",
    )

    start_marker = "    server_private = (await cmd(conn, f\"awk -F'=' "
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit("AmneziaWG unsafe awk parser was not found")
    end_marker = "    host = _node_host(node)\n"
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit("AmneziaWG host anchor was not found")

    replacement = '''    server_config = await cmd(
        conn,
        f"cat {shlex.quote(config)}",
        timeout=30,
    )
    server_private = _extract_awg_private_key(server_config)
    server_public = (
        await cmd(
            conn,
            f"printf '%s\\n' {shlex.quote(server_private)} | awg pubkey",
            timeout=30,
        )
    ).strip()
    if not _is_awg_key(server_public):
        raise StandaloneAccountError("AmneziaWG server public key is invalid")
'''
    text = text[:start] + replacement + text[end:]
    if "awk -F'='" in text:
        raise SystemExit("unsafe AmneziaWG key parser still exists")
    STANDALONE_PATH.write_text(text, encoding="utf-8")


def write_smoke() -> None:
    smoke = r'''from __future__ import annotations

import ast
import base64
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SINGBOX = ROOT / "backend/app/singbox_subscription_accounts.py"
STANDALONE = ROOT / "backend/app/standalone_subscription_accounts.py"
PROTOCOLS = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
}


def load_function(path: Path, name: str, namespace: dict):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


def singbox_regression() -> None:
    namespace = {
        "json": json,
        "TAGS": {protocol: f"twinpanel-{protocol}" for protocol in PROTOCOLS},
        "CONFIG_PATH": "/etc/twinpanel/sing-box/config.json",
        "REVOCATION_SENTINEL": "__twinpanel_revoked__",
    }
    mutation = load_function(SINGBOX, "_mutation_script", namespace)
    records = {
        "hysteria2": {"name": "tp-sub-17", "password": "pw"},
        "tuic": {
            "name": "tp-sub-17",
            "uuid": "00000000-0000-4000-8000-000000000017",
            "password": "pw",
        },
        "anytls": {"name": "tp-sub-17", "password": "pw"},
        "naive": {"username": "tp-sub-17", "password": "pw"},
        "shadowtls": {"name": "tp-sub-17", "password": "pw"},
        "snell": {"name": "tp-sub-17", "userkey": "user-key"},
    }
    for protocol in sorted(PROTOCOLS):
        apply_script = mutation(protocol, "tp-sub-17", records[protocol])
        revoke_script = mutation(protocol, "tp-sub-17", None)
        compile(apply_script, f"{protocol}-apply", "exec")
        compile(revoke_script, f"{protocol}-revoke", "exec")
        assert "users = [dict(" in revoke_script


def awg_regression() -> None:
    class StandaloneAccountError(RuntimeError):
        pass

    namespace = {
        "base64": base64,
        "StandaloneAccountError": StandaloneAccountError,
    }
    is_key = load_function(STANDALONE, "_is_awg_key", namespace)
    extract = load_function(STANDALONE, "_extract_awg_private_key", namespace)

    key = base64.b64encode(bytes(range(32))).decode("ascii")
    assert key.endswith("=")
    assert len(key) == 44
    assert is_key(key)
    config = (
        "[Interface]\n"
        "Address = 10.254.0.1/16\n"
        f"PrivateKey = {key}\n"
        "ListenPort = 8452\n"
    )
    assert extract(config) == key
    assert "awk -F'='" not in STANDALONE.read_text(encoding="utf-8")

    try:
        extract("[Interface]\nPrivateKey = truncated-key\n")
    except StandaloneAccountError:
        pass
    else:
        raise AssertionError("invalid AmneziaWG private key must fail closed")


if __name__ == "__main__":
    singbox_regression()
    awg_regression()
    print("MODERN_REAL_RUNTIME_PROVISIONING_V2_SMOKE=PASS")
'''
    SMOKE_PATH.write_text(smoke, encoding="utf-8")

    workflow = '''
    name: Modern Real Runtime Provisioning V2 Smoke

    on:
      pull_request:
        paths:
          - backend/app/singbox_subscription_accounts.py
          - backend/app/standalone_subscription_accounts.py
          - backend/tests/modern_real_runtime_provisioning_v2_smoke.py
          - .github/workflows/modern-real-runtime-provisioning-v2-smoke.yml
      workflow_dispatch:

    jobs:
      smoke:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with:
              python-version: '3.12'
          - name: Compile focused runtime modules
            run: |
              python -m py_compile backend/app/singbox_subscription_accounts.py
              python -m py_compile backend/app/standalone_subscription_accounts.py
              python -m py_compile backend/tests/modern_real_runtime_provisioning_v2_smoke.py
          - name: Execute regression smoke
            run: python backend/tests/modern_real_runtime_provisioning_v2_smoke.py
    '''
    SMOKE_WORKFLOW_PATH.write_text(textwrap.dedent(workflow).lstrip(), encoding="utf-8")


def main() -> None:
    patch_singbox()
    patch_amneziawg()
    write_smoke()
    ONE_SHOT_WORKFLOW_PATH.unlink()
    SELF_PATH.unlink()


if __name__ == "__main__":
    main()
