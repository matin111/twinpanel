from __future__ import annotations

import asyncio
import ipaddress
import shlex
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

from app import standalone_protocol_runtime as runtime


def _node(*, node_id: int, public_domain: str | None, public_ip: str | None):
    return SimpleNamespace(
        id=node_id,
        public_domain=public_domain,
        public_ip=public_ip,
    )


def _assert_dns_identity_contract() -> None:
    public_dns = _node(
        node_id=5,
        public_domain="vpn.example.com",
        public_ip="64.49.12.176",
    )
    assert runtime._trusttunnel_tls_hostname(public_dns) == "vpn.example.com"

    ip_only = _node(
        node_id=6,
        public_domain=None,
        public_ip="204.10.192.96",
    )
    synthetic = runtime._trusttunnel_tls_hostname(ip_only)
    assert synthetic == "tt-node-6.twinpanel.invalid"
    try:
        ipaddress.ip_address(synthetic)
    except ValueError:
        pass
    else:
        raise AssertionError("TrustTunnel TLS hostname must never be an IP literal")

    ip_as_domain = _node(
        node_id=1,
        public_domain="217.179.6.142",
        public_ip="217.179.6.142",
    )
    assert runtime._trusttunnel_tls_hostname(ip_as_domain) == "tt-node-1.twinpanel.invalid"

    no_id = _node(
        node_id=0,
        public_domain=None,
        public_ip="203.0.113.8",
    )
    assert runtime._trusttunnel_tls_hostname(no_id) == "tt-203-0-113-8.twinpanel.invalid"


def _assert_certificate_migration_command_contract() -> None:
    captured: list[tuple[str, int]] = []

    async def fake_cmd(_conn, command: str, *, timeout: int = 30, **_kwargs):
        captured.append((command, timeout))
        return ""

    original = runtime.cmd
    runtime.cmd = fake_cmd
    try:
        node = _node(
            node_id=6,
            public_domain=None,
            public_ip="204.10.192.96",
        )
        hostname, cert, key = asyncio.run(
            runtime._ensure_trusttunnel_cert(object(), node)
        )
    finally:
        runtime.cmd = original

    assert hostname == "tt-node-6.twinpanel.invalid"
    assert cert == "/etc/twinpanel/standalone/trusttunnel/server.crt"
    assert key == "/etc/twinpanel/standalone/trusttunnel/server.key"
    assert len(captured) == 1

    command, timeout = captured[0]
    assert timeout == 120
    assert "-checkhost" not in command
    assert "openssl x509" in command
    assert "-ext subjectAltName" in command
    assert "tr ','" in command
    assert "grep -Fqx DNS:tt-node-6.twinpanel.invalid" in command
    assert "subjectAltName=DNS:tt-node-6.twinpanel.invalid,IP:204.10.192.96" in command
    assert "server.crt.new" in command
    assert "server.key.new" in command
    assert "mv /etc/twinpanel/standalone/trusttunnel/server.key.new" in command
    assert "mv /etc/twinpanel/standalone/trusttunnel/server.crt.new" in command


def _make_cert(directory: Path, common_name: str, san: str, stem: str) -> Path:
    cert = directory / f"{stem}.crt"
    key = directory / f"{stem}.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:P-256",
            "-sha256",
            "-nodes",
            "-days",
            "1",
            "-subj",
            f"/CN={common_name}",
            "-addext",
            f"subjectAltName={san}",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return cert


def _exact_dns_san_present(cert: Path, hostname: str) -> bool:
    required = "DNS:" + hostname
    command = (
        f"openssl x509 -in {shlex.quote(str(cert))} -noout -ext subjectAltName 2>/dev/null "
        "| tr ',' '\\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' "
        f"| grep -Fqx {shlex.quote(required)}"
    )
    return subprocess.run(
        ["bash", "-c", command],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def _assert_real_certificate_san_regression() -> None:
    hostname = "tt-node-6.twinpanel.invalid"
    with tempfile.TemporaryDirectory(prefix="tt-san-v250-") as raw:
        directory = Path(raw)

        legacy_ip_only = _make_cert(
            directory,
            "204.10.192.96",
            "IP:204.10.192.96",
            "legacy-ip-only",
        )
        assert _exact_dns_san_present(legacy_ip_only, hostname) is False

        migrated = _make_cert(
            directory,
            hostname,
            f"DNS:{hostname},IP:204.10.192.96",
            "migrated",
        )
        assert _exact_dns_san_present(migrated, hostname) is True
        assert _exact_dns_san_present(migrated, "node-6.twinpanel.invalid") is False
        assert _exact_dns_san_present(migrated, "tt-node-6.twinpanel.invalid.evil") is False


def _assert_runtime_source_contract() -> None:
    assert runtime._is_dns_hostname("vpn.example.com") is True
    assert runtime._is_dns_hostname("217.179.6.142") is False
    assert runtime._is_dns_hostname("2001:db8::1") is False
    assert runtime._is_dns_hostname("bad host.example") is False
    assert runtime._is_dns_hostname("tt-node-1.twinpanel.invalid") is True


def main() -> None:
    _assert_dns_identity_contract()
    _assert_certificate_migration_command_contract()
    _assert_real_certificate_san_regression()
    _assert_runtime_source_contract()
    print("TRUSTTUNNEL_CERT_SAN_V250_SMOKE_OK")


if __name__ == "__main__":
    main()
