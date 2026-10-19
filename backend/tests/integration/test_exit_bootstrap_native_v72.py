from __future__ import annotations

import asyncio
import importlib.util
import os
import socket
import sys
from pathlib import Path

import asyncssh

# CI creates these RFC1918-only containers. This test never targets a public
# host and all authentication material is generated ephemerally by the job.
ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "backend" / "app" / "native_exit_bootstrap_v72.py"
os.environ["TWINPANEL_EXIT_HOSTKEY_DIR"] = "/tmp/twinpanel-v72-hostkeys"

spec = importlib.util.spec_from_file_location("native_exit_bootstrap_v72", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot_load_v72_transport")
transport = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = transport
spec.loader.exec_module(transport)

IRAN_HOST = "172.29.71.10"
EXIT_HOST = "172.29.72.20"
IRAN_KEY = os.environ["TP_V72_IRAN_KEY"]
EXIT_SECRET = os.environ["TP_V72_EXIT_SECRET"]


def assert_controller_isolated() -> None:
    try:
        socket.create_connection((EXIT_HOST, 22), timeout=2).close()
    except OSError:
        return
    raise AssertionError("controller_exit_direct_path_must_be_blocked")


async def open_iran():
    return await asyncssh.connect(
        IRAN_HOST,
        username="tpci",
        client_keys=[IRAN_KEY],
        known_hosts=None,
        connect_timeout=7,
        login_timeout=7,
    )


async def main() -> None:
    assert_controller_isolated()
    iran = await open_iran()
    reach = await iran.run(f"nc -z -w 3 {EXIT_HOST} 22", check=False)
    assert reach.exit_status == 0

    exit_conn = await transport.NativeIranExitConnection.open_with_password(
        iran,
        host=EXIT_HOST,
        port=22,
        username="tpci",
        password=EXIT_SECRET,
    )
    result = await exit_conn.run(
        "set -eu\nmkdir -p /tmp/twinpanel-v72-smoke\n"
        "printf '%s\\n' V72_NATIVE_BOOTSTRAP_OK > /tmp/twinpanel-v72-smoke/marker\n"
        "cat /tmp/twinpanel-v72-smoke/marker\n",
        check=True,
    )
    assert result.stdout.strip() == "V72_NATIVE_BOOTSTRAP_OK"

    process_list = await iran.run("ps -eo args", check=False)
    assert EXIT_SECRET not in (process_list.stdout or "")

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

    print("TOPOLOGY_CONTROLLER_TO_EXIT=DIRECT_BLOCKED")
    print("TOPOLOGY_CONTROLLER_TO_IRAN=SSH_OPEN")
    print("TOPOLOGY_IRAN_TO_EXIT=TCP_OPEN")
    print("EXIT_PASSWORD_NOT_IN_PROCESS_LIST=PASS")
    print("NATIVE_CONTROLMASTER_CLEANUP=PASS")
    print("EXIT_BOOTSTRAP_NATIVE_V72_INTEGRATION=PASS")


if __name__ == "__main__":
    asyncio.run(main())
