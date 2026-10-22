from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app import openvpn_runtime_v1 as runtime


class FakeProvision:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.install_calls = 0
        self.existing_calls = 0
        self.hook_ok = False

    async def cmd(self, _conn, command: str, check: bool = True):
        self.commands.append(command)
        if "TWINPANEL_OPENVPN_HOOK_OK" in command:
            return "TWINPANEL_OPENVPN_HOOK_OK" if self.hook_ok else ""
        if "systemctl restart openvpn-server@twinpanel.service" in command:
            self.hook_ok = True
        return ""

    async def active(self, _conn, *_services: str) -> bool:
        return True

    async def listener(self, _conn, _port: int, _transport: str) -> bool:
        return True

    async def install_openvpn(self, _conn, _port: int, _transport: str):
        self.install_calls += 1
        return True, None

    async def existing_ok(self, _conn, _protocol: str, _settings) -> bool:
        self.existing_calls += 1
        return True


async def main() -> None:
    fake = FakeProvision()
    original_install = fake.install_openvpn
    original_existing = fake.existing_ok

    runtime.install_openvpn_runtime_hooks(fake)
    assert fake.install_openvpn is not original_install
    assert fake.existing_ok is not original_existing

    # Hook installation is idempotent.
    wrapped_install = fake.install_openvpn
    wrapped_existing = fake.existing_ok
    runtime.install_openvpn_runtime_hooks(fake)
    assert fake.install_openvpn is wrapped_install
    assert fake.existing_ok is wrapped_existing

    # Fresh installs keep the legacy installer, then place and verify the hook
    # in a directory traversable by the nobody runtime user.
    fake.hook_ok = False
    ok, error = await fake.install_openvpn(object(), 21006, "udp")
    assert ok is True and error is None
    assert fake.install_calls == 1
    assert fake.hook_ok is True
    joined = "\n".join(fake.commands)
    assert runtime.HOOK_PATH in joined
    assert "chmod 0755" in joined
    assert "runuser -u nobody" in joined

    # Repair previously skipped OpenVPN when service+listener were healthy.
    # Now a broken hook is repaired in-place before existing_ok returns True.
    fake.commands.clear()
    fake.hook_ok = False
    settings = SimpleNamespace(openvpn_port=21006, openvpn_transport="udp")
    healthy = await fake.existing_ok(object(), "openvpn", settings)
    assert healthy is True
    assert fake.existing_calls == 1
    assert fake.hook_ok is True
    assert any(runtime.HOOK_PATH in command for command in fake.commands)

    # Non-OpenVPN protocol checks stay untouched.
    before = len(fake.commands)
    assert await fake.existing_ok(object(), "cisco", settings) is True
    assert len(fake.commands) == before

    print("OPENVPN_RUNTIME_V1_SMOKE=PASS")


if __name__ == "__main__":
    asyncio.run(main())
