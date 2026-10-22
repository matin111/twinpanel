from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app import modern_protocol_dispatch
from app.modern_protocol_dispatch import ModernRuntimeV2Error
from app.modern_protocol_preflight import (
    ensure_runtime_environment,
    transport_modes,
)


@dataclass
class Result:
    exit_status: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeConn:
    def __init__(self) -> None:
        self.commands: list[str] = []

    async def run(self, command: str, check: bool = False):
        del check
        self.commands.append(command)

        if "TMP_MODE=" in command and "twinpanel-runtime-apt" in command:
            return Result(
                stdout="TMP_MODE=1777\nTMP_REPAIRED=1\nAPT_TMP=ok\n",
            )

        if "ss -H -ltnp" in command and "sport = :8446" in command:
            return Result(
                stdout=(
                    'LISTEN 0 32768 *:8446 *:* '
                    'users:(("xray",pid=2271135,fd=7))\n'
                )
            )

        if "ss -H -ltnp" in command and "sport = :18446" in command:
            return Result(stdout="")

        return Result(stdout="")


async def _assert_environment_repair_contract() -> None:
    conn = FakeConn()
    result = await ensure_runtime_environment(conn)
    assert result == {
        "tmp_mode": "1777",
        "tmp_repaired": True,
        "apt_tmp": "ok",
    }
    assert len(conn.commands) == 1
    command = conn.commands[0]
    assert 'owner="$(stat -c' in command
    assert 'if [ "$owner" != "root:root" ]' in command
    assert "chmod 1777 /tmp" in command
    assert "twinpanel-runtime-root" in command
    assert "twinpanel-runtime-apt" in command
    assert "runuser -u _apt" in command


async def _assert_bulk_transport_aware_remap() -> None:
    conn = FakeConn()
    profiles = [
        {"protocol": "hysteria2", "port": 8444, "settings": {}},
        {"protocol": "anytls", "port": 8446, "settings": {}},
    ]

    async def unhealthy(_conn, protocol: str, port: int | None = None):
        return {
            "ok": False,
            "protocol": protocol,
            "service": "twinpanel-sing-box",
            "service_active": False,
            "listener": False,
            "port": port,
        }

    original = modern_protocol_dispatch._singbox_health
    modern_protocol_dispatch._singbox_health = unhealthy
    try:
        remaps = await modern_protocol_dispatch._reconcile_install_ports(
            conn,
            profiles,
        )
    finally:
        modern_protocol_dispatch._singbox_health = original

    # Xray owns TCP/8446, so AnyTLS moves. The same host could own TCP/8444,
    # but Hysteria2 is UDP and must not be moved because transports differ.
    assert profiles[0]["port"] == 8444
    assert profiles[1]["port"] == 18446
    assert set(remaps) == {"anytls"}
    assert remaps["anytls"]["from"] == 8446
    assert remaps["anytls"]["to"] == 18446
    assert remaps["anytls"]["transport"] == "tcp"
    assert "xray" in remaps["anytls"]["owner"]


async def _assert_single_apply_does_not_silently_remap() -> None:
    conn = FakeConn()
    profiles = [
        {"protocol": "anytls", "port": 8446, "settings": {}},
    ]

    async def unhealthy(_conn, protocol: str, port: int | None = None):
        return {"ok": False, "protocol": protocol, "port": port}

    original = modern_protocol_dispatch._singbox_health
    modern_protocol_dispatch._singbox_health = unhealthy
    try:
        try:
            await modern_protocol_dispatch._reconcile_install_ports(
                conn,
                profiles,
            )
        except ModernRuntimeV2Error as exc:
            message = str(exc)
        else:
            raise AssertionError("single apply unexpectedly auto-remapped a conflict")
    finally:
        modern_protocol_dispatch._singbox_health = original

    assert message.startswith("port_conflict:anytls:8446:")
    assert "xray" in message
    assert profiles[0]["port"] == 8446


def main() -> None:
    assert transport_modes("tcp") == ("tcp",)
    assert transport_modes("udp") == ("udp",)
    assert transport_modes("tcp_udp") == ("tcp", "udp")
    assert transport_modes("tcp_udp_quic") == ("tcp", "udp")
    assert transport_modes("quic") == ("udp",)

    asyncio.run(_assert_environment_repair_contract())
    asyncio.run(_assert_bulk_transport_aware_remap())
    asyncio.run(_assert_single_apply_does_not_silently_remap())

    print("MODERN_PROTOCOL_REMOTE_PREFLIGHT_SMOKE=PASS")


if __name__ == "__main__":
    main()
