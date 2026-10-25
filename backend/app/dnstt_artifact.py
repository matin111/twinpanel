from __future__ import annotations

import hashlib
import re
import shlex
from pathlib import Path
from typing import Any

from .netmod_udpgw_artifact import stage_netmod_udpgw


ARTIFACT_NAMES = {
    "amd64": "dnstt-server-linux-amd64",
    "arm64": "dnstt-server-linux-arm64",
}
NETMOD_DNSTT_REMOTE_NAME = "twinpanel-netmod-dnstt-server"


def _normalize_arch(value: str) -> str:
    machine = str(value or "").strip().lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    raise RuntimeError(f"dnstt_unsupported_architecture:{machine or 'unknown'}")


def _artifact_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts"


def artifact_for_machine(machine: str) -> tuple[Path, str, str]:
    arch = _normalize_arch(machine)
    name = ARTIFACT_NAMES[arch]
    artifact = _artifact_dir() / name
    sidecar = _artifact_dir() / f"{name}.sha256"

    if not artifact.is_file():
        raise RuntimeError(f"dnstt_artifact_missing:{artifact}")
    if not sidecar.is_file():
        raise RuntimeError(f"dnstt_checksum_missing:{sidecar}")

    expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError("dnstt_checksum_invalid")

    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(
            "dnstt_artifact_checksum_mismatch:"
            f"expected={expected}:actual={actual}"
        )

    return artifact, expected, arch


async def stage_dnstt_binary(conn: Any, remote_path: str) -> dict[str, str]:
    arch_result = await conn.run("uname -m", check=False, timeout=10)
    if int(getattr(arch_result, "exit_status", 1) or 0) != 0:
        detail = str(arch_result.stderr or arch_result.stdout or "uname failed").strip()
        raise RuntimeError(f"dnstt_remote_arch_failed:{detail[-500:]}")

    artifact, expected, arch = artifact_for_machine(str(arch_result.stdout or ""))
    remote = str(remote_path)
    tmp = f"{remote}.tmp"

    prepare = await conn.run(
        f"install -d -m 0755 {shlex.quote(str(Path(remote).parent))}",
        check=False,
        timeout=15,
    )
    if int(getattr(prepare, "exit_status", 1) or 0) != 0:
        detail = str(prepare.stderr or prepare.stdout or "binary directory failed").strip()
        raise RuntimeError(f"dnstt_remote_dir_failed:{detail[-800:]}")

    async with conn.start_sftp_client() as sftp:
        await sftp.put(str(artifact), tmp)

    install = await conn.run(
        " && ".join(
            [
                f"chmod 0755 {shlex.quote(tmp)}",
                f"test \"$(sha256sum {shlex.quote(tmp)} | awk '{{print $1}}')\" = {shlex.quote(expected)}",
                f"mv -f {shlex.quote(tmp)} {shlex.quote(remote)}",
            ]
        ),
        check=False,
        timeout=30,
    )
    if int(getattr(install, "exit_status", 1) or 0) != 0:
        await conn.run(f"rm -f {shlex.quote(tmp)}", check=False, timeout=10)
        detail = str(install.stderr or install.stdout or "binary install failed").strip()
        raise RuntimeError(f"dnstt_remote_artifact_install_failed:{detail[-1200:]}")

    result = {
        "arch": arch,
        "sha256": expected,
        "artifact": artifact.name,
        "remote_path": remote,
    }

    # NetMod VPN mode depends on a BadVPN-compatible UDP gateway reached via
    # an SSH direct-tcpip channel to 127.0.0.1:7300. Stage that companion only
    # for the NetMod DNSTT runtime; legacy/generic DNSTT installs stay unchanged.
    if Path(remote).name == NETMOD_DNSTT_REMOTE_NAME:
        udpgw = await stage_netmod_udpgw(conn)
        result.update(
            {
                "udpgw_arch": udpgw["arch"],
                "udpgw_sha256": udpgw["sha256"],
                "udpgw_artifact": udpgw["artifact"],
                "udpgw_remote_path": udpgw["remote_path"],
                "udpgw_service": udpgw["service"],
                "udpgw_listen": udpgw["listen"],
            }
        )

    return result
