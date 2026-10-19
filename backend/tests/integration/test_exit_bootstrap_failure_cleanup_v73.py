from __future__ import annotations

import asyncio
import os
import socket
import sys
from pathlib import Path

import asyncssh
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[3]
HOSTKEY_DIR = Path("/tmp/twinpanel-v73-hostkeys")
os.environ["TWINPANEL_EXIT_HOSTKEY_DIR"] = str(HOSTKEY_DIR)
sys.path.insert(0, str(ROOT / "backend"))

from app import native_exit_bootstrap_v72 as v72  # noqa: E402
from app import native_exit_bootstrap_v73 as v73  # noqa: E402


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


async def assert_iran_bootstrap_clean(iran) -> None:
    workspaces = await iran.run(
        "find /run/twinpanel-bootstrap -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null",
        check=False,
    )
    assert not (workspaces.stdout or "").strip(), workspaces.stdout

    masters = await iran.run(
        "ps -eo pid=,args= | "
        "awk '/ssh/ && /\\/run\\/twinpanel-bootstrap\\// && $0 !~ /awk/'",
        check=False,
    )
    assert not (masters.stdout or "").strip(), masters.stdout


async def main() -> None:
    HOSTKEY_DIR.mkdir(parents=True, exist_ok=True)
    for path in HOSTKEY_DIR.glob("*"):
        path.unlink()

    assert_controller_isolated()

    iran = await open_iran()
    reach = await iran.run(f"nc -z -w 3 {EXIT_HOST} 22", check=False)
    assert reach.exit_status == 0
    await assert_iran_bootstrap_clean(iran)

    # 1) Authentication failure: V72 created the workspace before auth. V73
    # must remove it even though no connection object is returned to the caller.
    try:
        await v73.NativeIranExitConnection.open_with_password(
            iran,
            host=EXIT_HOST,
            port=22,
            username="tpci",
            password="v73-invalid-password",
        )
    except v72.NativeBootstrapError as exc:
        assert exc.stage == "exit_auth", (exc.stage, exc.detail)
    else:
        raise AssertionError("invalid_exit_auth_unexpectedly_succeeded")
    await assert_iran_bootstrap_clean(iran)

    # 2) Iran -> Exit TCP failure must also leave no workspace/process behind.
    try:
        await v73.NativeIranExitConnection.open_with_password(
            iran,
            host=EXIT_HOST,
            port=65000,
            username="tpci",
            password=EXIT_TEST_SECRET,
        )
    except v72.NativeBootstrapError as exc:
        assert exc.stage == "iran_to_exit_tcp", (exc.stage, exc.detail)
    else:
        raise AssertionError("closed_exit_port_unexpectedly_succeeded")
    await assert_iran_bootstrap_clean(iran)

    # 3) Reproduce the subtle post-auth case: native OpenSSH successfully opens
    # a ControlMaster, then a controller-side host-key persistence error occurs.
    # V73 must explicitly close that master and remove its workspace.
    original_store = v72._store_pinned_hostkey

    def fail_store(_host: str, _port: int, _content: str) -> None:
        raise v72.NativeBootstrapError("exit_host_key", "ci_forced_store_failure")

    v72._store_pinned_hostkey = fail_store
    try:
        try:
            await v73.NativeIranExitConnection.open_with_password(
                iran,
                host=EXIT_HOST,
                port=22,
                username="tpci",
                password=EXIT_TEST_SECRET,
            )
        except v72.NativeBootstrapError as exc:
            assert exc.stage == "exit_host_key", (exc.stage, exc.detail)
        else:
            raise AssertionError("forced_hostkey_store_failure_unexpectedly_succeeded")
    finally:
        v72._store_pinned_hostkey = original_store
    await assert_iran_bootstrap_clean(iran)

    # 4) The hardened transport must still complete the intended real topology
    # path and clean normally after an installer-like command.
    exit_conn = await v73.NativeIranExitConnection.open_with_password(
        iran,
        host=EXIT_HOST,
        port=22,
        username="tpci",
        password=EXIT_TEST_SECRET,
    )
    result = await exit_conn.run(
        "set -eu\n"
        "mkdir -p /tmp/twinpanel-v73-smoke\n"
        "printf '%s\\n' V73_NATIVE_BOOTSTRAP_OK > /tmp/twinpanel-v73-smoke/marker\n"
        "cat /tmp/twinpanel-v73-smoke/marker\n",
        check=True,
    )
    assert result.stdout.strip() == "V73_NATIVE_BOOTSTRAP_OK"

    process_list = await iran.run("ps -eo args", check=False)
    assert EXIT_TEST_SECRET not in (process_list.stdout or "")

    exit_conn.close()
    await exit_conn.wait_closed()

    # wait_closed() closes the parent Iran connection, so open a fresh one for
    # the final orphan check.
    iran = await open_iran()
    await assert_iran_bootstrap_clean(iran)
    iran.close()
    await iran.wait_closed()

    print("TOPOLOGY_CONTROLLER_TO_EXIT=DIRECT_BLOCKED")
    print("TOPOLOGY_CONTROLLER_TO_IRAN=SSH_OPEN")
    print("TOPOLOGY_IRAN_TO_EXIT=TCP_OPEN")
    print("FAILED_AUTH_CLEANUP=PASS")
    print("FAILED_TCP_CLEANUP=PASS")
    print("POST_AUTH_HOSTKEY_FAILURE_CLEANUP=PASS")
    print("EXIT_PASSWORD_NOT_IN_PROCESS_LIST=PASS")
    print("SUCCESSFUL_CONTROLMASTER_CLEANUP=PASS")
    print("EXIT_BOOTSTRAP_FAILURE_CLEANUP_V73=PASS")


if __name__ == "__main__":
    asyncio.run(main())
