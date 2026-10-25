from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = REPO_ROOT / "scripts/build-netmod-udpgw.sh"
PATCHER = REPO_ROOT / "scripts/patch-badvpn-udpgw-resolver.py"


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


def test_udpgw_remote_repair_requires_real_resolver_before_success():
    script = udpgw_artifact._service_install_script()
    assert "--listen-addr 127.0.0.1:17301" in script
    assert "--logger stdout" in script
    assert "--loglevel info" in script
    assert "no name servers available" in script
    assert "using DNS server" in script
    assert "NETMOD_UDPGW_DNS_RESOLVER_UNAVAILABLE" in script
    assert "NETMOD_UDPGW_DNS_RESOLVER_NOT_CONFIRMED" in script
    assert "UDPGW_DNS_RESOLVER=yes" in script


def test_stage_udpgw_verifies_binary_then_installs_managed_service():
    with tempfile.TemporaryDirectory() as temp:
        fake_binary = Path(temp) / "badvpn-udpgw-linux-amd64"
        fake_binary.write_bytes(b"verified-test-binary")
        with patch.object(
            udpgw_artifact,
            "artifact_for_machine",
            return_value=(fake_binary, "a" * 64, "amd64"),
        ):
            conn = _FakeConn()
            result = asyncio.run(udpgw_artifact.stage_netmod_udpgw(conn))

    assert result["arch"] == "amd64"
    assert result["service"] == NETMOD_UDPGW_SERVICE
    assert result["listen"] == NETMOD_UDPGW_LISTEN
    assert result["dns_resolver"] == "verified"
    assert conn.puts == [(str(fake_binary), NETMOD_UDPGW_BINARY + ".tmp")]
    joined = "\n".join(conn.commands)
    assert "sha256sum" in joined
    assert NETMOD_UDPGW_BINARY in joined
    assert "systemctl restart" in joined
    assert NETMOD_UDPGW_LISTEN in joined
    assert "using DNS server" in joined


def test_netmod_dnstt_stages_udpgw_companion_only_for_netmod():
    with tempfile.TemporaryDirectory() as temp:
        fake_dnstt = Path(temp) / "dnstt-server-linux-amd64"
        fake_dnstt.write_bytes(b"verified-dnstt")
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
                "dns_resolver": "verified",
            }

        with patch.object(
            dnstt_artifact,
            "artifact_for_machine",
            return_value=(fake_dnstt, "b" * 64, "amd64"),
        ), patch.object(dnstt_artifact, "stage_netmod_udpgw", fake_stage_udpgw):
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


def test_resolver_transformer_preserves_upstream_first_and_adds_ipv4_fallback():
    patcher = PATCHER.read_text(encoding="utf-8")
    assert "/etc/resolv.conf" in patcher
    assert "res_init() == 0 && _res.nscount > 0" in patcher
    assert "inet_pton(AF_INET, value, &ipv4)" in patcher
    assert 'strcmp(key, \\"nameserver\\")' in patcher
    assert "BAddr_InitIPv4(out, ipv4.s_addr, hton16(53))" in patcher
    assert "loaded DNS server from /etc/resolv.conf fallback" in patcher
    assert "no name servers available" in patcher
    assert "BADVPN_PATCH_" in patcher
    assert "count != 1" in patcher


def test_resolver_aware_build_script_uses_deterministic_glibc_static_transformer():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert BADVPN_COMMIT in script
    assert "patch-badvpn-udpgw-resolver.py" in script
    assert 'python3 "$PATCHER" "$SRC/udpgw/udpgw.c"' in script
    assert "CC=gcc cmake" in script
    assert "-DCMAKE_EXE_LINKER_FLAGS='-static'" in script
    assert "statically linked" in script
    assert "using DNS server" in script
    assert "no name servers available" in script
    assert "NETMOD_UDPGW_RESOLVER_UNAVAILABLE" in script
    assert "NETMOD_UDPGW_RESOLVER=verified" in script


def test_release_pipeline_uses_shared_resolver_aware_builder_and_license():
    workflow = (REPO_ROOT / ".github/workflows/publish-prebuilt-release.yml").read_text(encoding="utf-8")
    assert "Build verified NetMod UDPGW artifact" in workflow
    assert "scripts/build-netmod-udpgw.sh" in workflow
    assert "badvpn-udpgw-linux-amd64" in workflow
    assert "badvpn-udpgw-linux-amd64.sha256" in workflow
    assert "badvpn-COPYING" in workflow
    assert "libc6-dev" in workflow


def test_dedicated_ci_uses_shared_v235_transformer_builder():
    dedicated = (REPO_ROOT / ".github/workflows/netmod-udpgw-v231-smoke.yml").read_text(encoding="utf-8")
    assert "scripts/build-netmod-udpgw.sh" in dedicated
    assert "scripts/patch-badvpn-udpgw-resolver.py" in dedicated
    assert "libc6-dev" in dedicated
    assert "Resolver V235" in dedicated
    assert "NETMOD_UDPGW_RESOLVER=verified" in dedicated
    assert "using DNS server" in dedicated


def test_admin_ui_does_not_offer_mtu_above_verified_requester_size():
    panel = (REPO_ROOT / "components/dns-emergency-panel.tsx").read_text(encoding="utf-8")
    assert '<option value={1232}>1232 · Verified default</option>' in panel
    assert '<option value={512}>512 · Compatibility</option>' in panel
    assert "<option value={1400}>" not in panel
    assert "<option value={1452}>" not in panel


def main() -> int:
    test_udpgw_runtime_contract_is_private_and_pinned()
    test_udpgw_service_is_loopback_only_self_healing_and_bounds_clients()
    test_udpgw_remote_repair_requires_real_resolver_before_success()
    test_stage_udpgw_verifies_binary_then_installs_managed_service()
    test_netmod_dnstt_stages_udpgw_companion_only_for_netmod()
    test_resolver_transformer_preserves_upstream_first_and_adds_ipv4_fallback()
    test_resolver_aware_build_script_uses_deterministic_glibc_static_transformer()
    test_release_pipeline_uses_shared_resolver_aware_builder_and_license()
    test_dedicated_ci_uses_shared_v235_transformer_builder()
    test_admin_ui_does_not_offer_mtu_above_verified_requester_size()
    print("NETMOD_UDPGW_V235_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
