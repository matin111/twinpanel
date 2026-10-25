from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import app.dnstt_artifact as dnstt_artifact
import app.netmod_udpgw_artifact as udpgw_artifact
from app.netmod_udpgw import (
    BADVPN_COMMIT,
    NETMOD_DNSTT_SAFE_MTU,
    NETMOD_SSH_UDPGW_DROPIN,
    NETMOD_UDPGW_BINARY,
    NETMOD_UDPGW_LISTEN,
    NETMOD_UDPGW_SERVICE,
)


class _FakeSftp:
    def __init__(self, puts: list[tuple[str, str]]):
        self.puts = puts

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def put(self, source: str, target: str):
        self.puts.append((source, target))


class _FakeConn:
    def __init__(self):
        self.commands: list[str] = []
        self.puts: list[tuple[str, str]] = []

    async def run(self, command: str, **kwargs):
        self.commands.append(command)
        if command == "uname -m":
            return SimpleNamespace(exit_status=0, stdout="x86_64\n", stderr="")
        return SimpleNamespace(exit_status=0, stdout="", stderr="")

    def start_sftp_client(self):
        return _FakeSftp(self.puts)


def test_udpgw_runtime_contract_is_private_and_pinned():
    assert NETMOD_UDPGW_LISTEN == "127.0.0.1:7300"
    assert NETMOD_UDPGW_SERVICE == "twinpanel-netmod-udpgw.service"
    assert NETMOD_UDPGW_BINARY == "/usr/local/bin/twinpanel-netmod-udpgw"
    assert len(BADVPN_COMMIT) == 40
    int(BADVPN_COMMIT, 16)
    assert NETMOD_DNSTT_SAFE_MTU == 1232


def test_udpgw_service_is_loopback_only_self_healing_and_bounds_clients():
    script = udpgw_artifact._service_install_script()
    assert "--listen-addr 127.0.0.1:7300" in script
    assert "--max-clients 256" in script
    assert "--max-connections-for-client 512" in script
    assert "Restart=always" in script
    assert "NoNewPrivileges=true" in script
    assert "ProtectSystem=strict" in script
    assert "0.0.0.0:7300" not in script
    assert NETMOD_SSH_UDPGW_DROPIN in script
    assert "Requires=twinpanel-netmod-udpgw.service" in script
    assert "After=twinpanel-netmod-udpgw.service" in script
    assert "-gt 1232" in script
    assert "10-performance.conf" in script


def test_stage_udpgw_verifies_binary_then_installs_managed_service(monkeypatch, tmp_path):
    fake_binary = tmp_path / "badvpn-udpgw-linux-amd64"
    fake_binary.write_bytes(b"verified-test-binary")
    monkeypatch.setattr(
        udpgw_artifact,
        "artifact_for_machine",
        lambda machine: (fake_binary, "a" * 64, "amd64"),
    )
    conn = _FakeConn()
    result = asyncio.run(udpgw_artifact.stage_netmod_udpgw(conn))

    assert result["arch"] == "amd64"
    assert result["service"] == NETMOD_UDPGW_SERVICE
    assert result["listen"] == NETMOD_UDPGW_LISTEN
    assert conn.puts == [(str(fake_binary), NETMOD_UDPGW_BINARY + ".tmp")]
    joined = "\n".join(conn.commands)
    assert "sha256sum" in joined
    assert NETMOD_UDPGW_BINARY in joined
    assert "systemctl restart" in joined
    assert NETMOD_UDPGW_LISTEN in joined


def test_netmod_dnstt_stages_udpgw_companion_only_for_netmod(monkeypatch, tmp_path):
    fake_dnstt = tmp_path / "dnstt-server-linux-amd64"
    fake_dnstt.write_bytes(b"verified-dnstt")
    monkeypatch.setattr(
        dnstt_artifact,
        "artifact_for_machine",
        lambda machine: (fake_dnstt, "b" * 64, "amd64"),
    )
    calls: list[bool] = []

    async def fake_stage_udpgw(conn):
        calls.append(True)
        return {
            "arch": "amd64",
            "sha256": "c" * 64,
            "artifact": "badvpn-udpgw-linux-amd64",
            "remote_path": NETMOD_UDPGW_BINARY,
            "service": NETMOD_UDPGW_SERVICE,
            "listen": NETMOD_UDPGW_LISTEN,
        }

    monkeypatch.setattr(dnstt_artifact, "stage_netmod_udpgw", fake_stage_udpgw)

    conn = _FakeConn()
    result = asyncio.run(
        dnstt_artifact.stage_dnstt_binary(
            conn,
            "/usr/local/bin/twinpanel-netmod-dnstt-server",
        )
    )
    assert calls == [True]
    assert result["udpgw_service"] == NETMOD_UDPGW_SERVICE

    calls.clear()
    conn2 = _FakeConn()
    result2 = asyncio.run(
        dnstt_artifact.stage_dnstt_binary(
            conn2,
            "/usr/local/bin/twinpanel-dnstt-server",
        )
    )
    assert calls == []
    assert "udpgw_service" not in result2
