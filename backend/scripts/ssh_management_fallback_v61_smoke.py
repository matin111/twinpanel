#!/usr/bin/env python3

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from types import SimpleNamespace

from app import ssh_management_fallback_v61 as fallback
from app.routers import provision


def main() -> None:
    assert provision.ssh_connect_saved is fallback.ssh_connect_saved_v61

    # Tunnel #1 Kernel GRE deterministic runtime is the exact production
    # management path validated during the incident: Iran .5 -> Exit .6.
    assert fallback._runtime_exit_ip("kernel_gre", 1) == "10.248.0.6"

    relay_node = SimpleNamespace(id=2, public_ip="193.39.9.222")
    relay_access = SimpleNamespace(
        private_key_path="/var/lib/vpnshop/node-keys/node-2.key",
        ssh_username="root",
        ssh_port=22,
    )

    command = fallback._proxy_command(
        relay_node,
        relay_access,
        "10.248.0.6",
        22,
    )
    argv = shlex.split(command)

    assert argv[0] == "ssh"
    assert "-T" in argv
    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=no" in argv
    assert "193.39.9.222" in " ".join(argv)
    assert argv[-3:] == ["nc", "10.248.0.6", "22"]
    assert "-w" not in argv[-5:]
    assert "password" not in command.lower()

    asyncio.run(_relay_retry_contract(relay_node, relay_access))

    print("SSH_MANAGEMENT_FALLBACK_V62_SMOKE=OK")
    print("KERNEL_GRE_TUNNEL_1_EXIT_IP=10.248.0.6")
    print("MANAGEMENT_PATH=controller->iran-ssh->nc->exit-private-ssh")
    print("RELAY_RETRY=FIRST_CONNECTION_LOST_SECOND_SUCCESS")


async def _relay_retry_contract(relay_node, relay_access) -> None:
    calls = []
    original_connect = fallback.asyncssh.connect
    original_delay = fallback._RELAY_RETRY_DELAY_SECONDS

    class FakeConnection:
        pass

    async def fake_connect(host, **kwargs):
        calls.append((host, kwargs))
        if len(calls) == 1:
            raise ConnectionError("Connection lost")
        return FakeConnection()

    fallback.asyncssh.connect = fake_connect
    fallback._RELAY_RETRY_DELAY_SECONDS = 0

    try:
        node = SimpleNamespace(public_ip="64.49.12.176")
        access = SimpleNamespace(ssh_port=22, ssh_username="root")
        candidate = {
            "relay_node": relay_node,
            "relay_access": relay_access,
            "target_ip": "10.248.0.6",
            "transport": "kernel_gre",
            "tunnel_id": 1,
        }

        result = await fallback._relay_connect(
            node,
            access,
            Path("/var/lib/vpnshop/node-keys/node-3.key"),
            candidate,
        )

        assert isinstance(result, FakeConnection)
        assert len(calls) == 2

        for host, kwargs in calls:
            assert host == "10.248.0.6"
            assert kwargs["port"] == 22
            assert kwargs["username"] == "root"
            assert kwargs["known_hosts"] is None
            assert kwargs["client_keys"] == [
                "/var/lib/vpnshop/node-keys/node-3.key"
            ]
            assert "proxy_command" in kwargs
            assert "193.39.9.222" in kwargs["proxy_command"]
            assert "10.248.0.6" in kwargs["proxy_command"]
            assert "nc -w" not in kwargs["proxy_command"]
            assert kwargs["connect_timeout"] <= 10
            assert kwargs["login_timeout"] <= 10

    finally:
        fallback.asyncssh.connect = original_connect
        fallback._RELAY_RETRY_DELAY_SECONDS = original_delay


if __name__ == "__main__":
    main()
