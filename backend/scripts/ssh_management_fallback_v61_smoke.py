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
    assert "BatchMode=yes" in argv
    assert "StrictHostKeyChecking=no" in argv
    assert "193.39.9.222" in " ".join(argv)
    assert argv[-5:] == ["nc", "-w", "10", "10.248.0.6", "22"]
    assert "password" not in command.lower()

    asyncio.run(_relay_connect_contract(relay_node, relay_access))

    print("SSH_MANAGEMENT_FALLBACK_V61_SMOKE=OK")
    print("KERNEL_GRE_TUNNEL_1_EXIT_IP=10.248.0.6")
    print("MANAGEMENT_PATH=controller->iran-ssh->nc->exit-private-ssh")


async def _relay_connect_contract(relay_node, relay_access) -> None:
    calls = []
    original_connect = fallback.asyncssh.connect

    class FakeConnection:
        pass

    async def fake_connect(host, **kwargs):
        calls.append((host, kwargs))
        return FakeConnection()

    fallback.asyncssh.connect = fake_connect

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
        assert len(calls) == 1

        host, kwargs = calls[0]
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
        assert kwargs["connect_timeout"] <= 15
        assert kwargs["login_timeout"] <= 15

    finally:
        fallback.asyncssh.connect = original_connect


if __name__ == "__main__":
    main()
