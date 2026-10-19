from __future__ import annotations

import asyncio
import base64
import importlib.util
import os
import socket
import sys
from pathlib import Path

import asyncssh
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# CI creates these RFC1918-only containers. This test never targets a public
# host. The deterministic key and password below belong only to the disposable
# container image built by this workflow.
ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "backend" / "app" / "native_exit_bootstrap_v72.py"
HOSTKEY_DIR = Path("/tmp/twinpanel-v72-hostkeys")
os.environ["TWINPANEL_EXIT_HOSTKEY_DIR"] = str(HOSTKEY_DIR)

spec = importlib.util.spec_from_file_location("native_exit_bootstrap_v72", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot_load_v72_transport")
transport = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = transport
spec.loader.exec_module(transport)

IRAN_HOST = "172.29.71.10"
EXIT_HOST = "172.29.72.20"
EXIT_TEST_SECRET = "v72-ci-exit-secret"
IRAN_TEST_KEY = Ed25519PrivateKey.from_private_bytes(b"B" * 32)
IRAN_TEST_KEY_PEM = IRAN_TEST_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.OpenSSH,
    serialization.NoEncryption(),
)


def assert_controller_isolated() -> None:
    try:
        socket.create_connection((EXIT_HOST, 22), timeout=2).close()
    except OSError:
        return
    raise AssertionError("controller_exit_direct_path_must_be_blocked")


async def open_iran():
    key = asyncssh.import_private_key(IRAN_TEST_KEY_PEM)
    return await asyncssh.connect(
        IRAN_HOST,
        username="tpci",
        client_keys=[key],
        known_hosts=None,
        connect_timeout=7,
        login_timeout=7,
    )


async def main() -> None:
    HOSTKEY_DIR.mkdir(parents=True, exist_ok=True)
    assert_controller_isolated()

    iran = await open_iran()
    reach = await iran.run(f"nc -z -w 3 {EXIT_HOST} 22", check=False)
    assert reach.exit_status == 0

    exit_conn = await transport.NativeIranExitConnection.open_with_password(
        iran,
        host=EXIT_HOST,
        port=22,
        username="tpci",
        password=EXIT_TEST_SECRET,
    )
    result = await exit_conn.run(
        "set -eu\nmkdir -p /tmp/twinpanel-v72-smoke\n"
        "printf '%s\\n' V72_NATIVE_BOOTSTRAP_OK > /tmp/twinpanel-v72-smoke/marker\n"
        "cat /tmp/twinpanel-v72-smoke/marker\n",
        check=True,
    )
    assert result.stdout.strip() == "V72_NATIVE_BOOTSTRAP_OK"

    # Password and installer body are transported over stdin, not argv.
    process_list = await iran.run("ps -eo args", check=False)
    assert EXIT_TEST_SECRET not in (process_list.stdout or "")

    # Stage a disposable Exit key, then prove the saved-key fallback path too.
    exit_key = asyncssh.generate_private_key("ssh-ed25519")
    exit_private = exit_key.export_private_key(format_name="openssh").decode()
    exit_public = exit_key.export_public_key(format_name="openssh").decode().strip()
    encoded_pub = base64.b64encode(exit_public.encode()).decode()
    await exit_conn.run(
        "set -eu\nmkdir -p ~/.ssh\nchmod 700 ~/.ssh\n"
        "touch ~/.ssh/authorized_keys\nchmod 600 ~/.ssh/authorized_keys\n"
        f"PUB=$(printf '%s' {encoded_pub} | base64 -d)\n"
        "grep -qxF \"$PUB\" ~/.ssh/authorized_keys || printf '%s\\n' \"$PUB\" >> ~/.ssh/authorized_keys\n",
        check=True,
    )

    token = exit_conn.token
    exit_conn.close()
    await exit_conn.wait_closed()

    iran = await open_iran()
    cleanup = await iran.run(
        f"test ! -e /run/twinpanel-bootstrap/{token} && "
        f"! ps -eo args | grep -F {token} | grep -v grep",
        check=False,
    )
    assert cleanup.exit_status == 0
    iran.close()
    await iran.wait_closed()

    iran = await open_iran()
    saved = await transport.NativeIranExitConnection.open_with_private_key(
        iran,
        host=EXIT_HOST,
        port=22,
        username="tpci",
        private_key=exit_private,
    )
    verify = await saved.run("cat /tmp/twinpanel-v72-smoke/marker", check=True)
    assert verify.stdout.strip() == "V72_NATIVE_BOOTSTRAP_OK"
    process_list = await iran.run("ps -eo args", check=False)
    assert "BEGIN OPENSSH PRIVATE KEY" not in (process_list.stdout or "")
    saved.close()
    await saved.wait_closed()

    wrong = await open_iran()
    try:
        await transport.NativeIranExitConnection.open_with_password(
            wrong,
            host=EXIT_HOST,
            port=22,
            username="tpci",
            password="v72-ci-invalid-auth",
        )
    except transport.NativeBootstrapError as exc:
        assert exc.stage == "exit_auth", (exc.stage, exc.detail)
    else:
        raise AssertionError("invalid_exit_auth_unexpectedly_succeeded")
    finally:
        wrong.close()
        await wrong.wait_closed()

    dead = await open_iran()
    try:
        await transport.NativeIranExitConnection.open_with_password(
            dead,
            host=EXIT_HOST,
            port=65000,
            username="tpci",
            password=EXIT_TEST_SECRET,
        )
    except transport.NativeBootstrapError as exc:
        assert exc.stage == "iran_to_exit_tcp", (exc.stage, exc.detail)
    else:
        raise AssertionError("closed_exit_port_unexpectedly_succeeded")
    finally:
        dead.close()
        await dead.wait_closed()

    assert list(HOSTKEY_DIR.glob("*.known_hosts"))
    print("TOPOLOGY_CONTROLLER_TO_EXIT=DIRECT_BLOCKED")
    print("TOPOLOGY_CONTROLLER_TO_IRAN=SSH_OPEN")
    print("TOPOLOGY_IRAN_TO_EXIT=TCP_OPEN")
    print("EXIT_PASSWORD_NOT_IN_PROCESS_LIST=PASS")
    print("SAVED_KEY_NATIVE_FALLBACK=PASS")
    print("ERROR_STAGE_EXIT_AUTH=PASS")
    print("ERROR_STAGE_IRAN_TO_EXIT_TCP=PASS")
    print("HOSTKEY_TOFU_PINNING=PASS")
    print("NATIVE_CONTROLMASTER_CLEANUP=PASS")
    print("EXIT_BOOTSTRAP_NATIVE_V72_INTEGRATION=PASS")


if __name__ == "__main__":
    asyncio.run(main())
