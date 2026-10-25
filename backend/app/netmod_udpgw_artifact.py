from __future__ import annotations

import hashlib
import re
import shlex
from pathlib import Path
from typing import Any

from .netmod_udpgw import (
    NETMOD_DNSTT_PERFORMANCE_DROPIN,
    NETMOD_DNSTT_SAFE_MTU,
    NETMOD_SSH_UDPGW_DROPIN,
    NETMOD_UDPGW_BINARY,
    NETMOD_UDPGW_LISTEN,
    NETMOD_UDPGW_SERVICE,
)


ARTIFACT_NAMES = {
    "amd64": "badvpn-udpgw-linux-amd64",
}


def _normalize_arch(value: str) -> str:
    machine = str(value or "").strip().lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    raise RuntimeError(f"netmod_udpgw_unsupported_architecture:{machine or 'unknown'}")


def _artifact_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "artifacts"


def artifact_for_machine(machine: str) -> tuple[Path, str, str]:
    arch = _normalize_arch(machine)
    name = ARTIFACT_NAMES[arch]
    artifact = _artifact_dir() / name
    sidecar = _artifact_dir() / f"{name}.sha256"

    if not artifact.is_file():
        raise RuntimeError(f"netmod_udpgw_artifact_missing:{artifact}")
    if not sidecar.is_file():
        raise RuntimeError(f"netmod_udpgw_checksum_missing:{sidecar}")

    expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError("netmod_udpgw_checksum_invalid")

    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(
            "netmod_udpgw_artifact_checksum_mismatch:"
            f"expected={expected}:actual={actual}"
        )

    return artifact, expected, arch


def _service_install_script() -> str:
    q_binary = shlex.quote(NETMOD_UDPGW_BINARY)
    q_service = shlex.quote(NETMOD_UDPGW_SERVICE)
    q_dropin = shlex.quote(NETMOD_SSH_UDPGW_DROPIN)
    q_perf = shlex.quote(NETMOD_DNSTT_PERFORMANCE_DROPIN)
    return f"""set -Eeuo pipefail

# A listener alone is not sufficient for NetMod VPN mode. BadVPN's DNS path
# calls res_init() and requires at least one resolver. Production proved the old
# musl-static artifact could listen while reporting 'no name servers available'.
# Probe the exact staged binary on the real Exit before accepting the repair.
probe_log="$(mktemp)"
probe_pid=""
cleanup_probe() {{
  if [ -n "$probe_pid" ]; then
    kill "$probe_pid" >/dev/null 2>&1 || true
    wait "$probe_pid" >/dev/null 2>&1 || true
  fi
  rm -f "$probe_log"
}}
trap cleanup_probe EXIT
{q_binary} --logger stdout --loglevel info --listen-addr 127.0.0.1:17301 --max-clients 4 --max-connections-for-client 8 >"$probe_log" 2>&1 &
probe_pid=$!
for _ in $(seq 1 30); do
  if ss -H -ltn 2>/dev/null | grep -F '127.0.0.1:17301 ' >/dev/null; then
    break
  fi
  if ! kill -0 "$probe_pid" >/dev/null 2>&1; then
    cat "$probe_log" >&2 || true
    echo NETMOD_UDPGW_PROBE_EXITED_EARLY >&2
    exit 37
  fi
  sleep 0.1
done
if ! ss -H -ltn 2>/dev/null | grep -F '127.0.0.1:17301 ' >/dev/null; then
  cat "$probe_log" >&2 || true
  echo NETMOD_UDPGW_PROBE_LISTENER_MISSING >&2
  exit 38
fi

# stdout is block-buffered when redirected. Stop the short-lived probe first so
# BadVPN flushes its resolver INFO/ERROR messages before we inspect the log.
sleep 0.2
kill "$probe_pid" >/dev/null 2>&1 || true
wait "$probe_pid" >/dev/null 2>&1 || true
probe_pid=""

if grep -Fq 'no name servers available' "$probe_log"; then
  cat "$probe_log" >&2 || true
  echo NETMOD_UDPGW_DNS_RESOLVER_UNAVAILABLE >&2
  exit 39
fi
if ! grep -Fq 'using DNS server' "$probe_log"; then
  cat "$probe_log" >&2 || true
  echo NETMOD_UDPGW_DNS_RESOLVER_NOT_CONFIRMED >&2
  exit 40
fi
rm -f "$probe_log"
trap - EXIT

# NetMod's VPN-mode UDP path reaches the remote UDP gateway through an SSH
# direct-tcpip channel to loopback:7300. Keep the gateway private to loopback.
cat > /etc/systemd/system/{NETMOD_UDPGW_SERVICE} <<'UNIT'
[Unit]
Description=TwinPanel NetMod UDP gateway
After=network-online.target
Wants=network-online.target
PartOf=twinpanel-netmod-ssh.service

[Service]
Type=simple
ExecStart={NETMOD_UDPGW_BINARY} --loglevel warning --listen-addr {NETMOD_UDPGW_LISTEN} --max-clients 256 --max-connections-for-client 512
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
LockPersonality=true
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT

install -d -m 0755 "$(dirname {q_dropin})"
cat > {q_dropin} <<'UNIT'
[Unit]
Requires=twinpanel-netmod-udpgw.service
BindsTo=twinpanel-netmod-udpgw.service
After=twinpanel-netmod-udpgw.service
UNIT

# Production evidence from the real NetMod client showed requester payload 1232.
# Any larger persisted Performance Lab override makes DNSTT reject requests with
# FORMERR. Fail closed to the known-compatible default during repair/install.
if [ -s {q_perf} ]; then
  configured="$(grep -oE -- '-mtu [0-9]+' {q_perf} 2>/dev/null | tail -n1 | awk '{{print $2}}' || true)"
  case "$configured" in
    ''|*[!0-9]*) ;;
    *)
      if [ "$configured" -gt {NETMOD_DNSTT_SAFE_MTU} ]; then
        rm -f {q_perf}
      fi
      ;;
  esac
fi

systemctl daemon-reload
systemctl restart {q_service}
sleep 1
systemctl is-active --quiet {q_service}
ss -H -ltnp 2>/dev/null | grep -F '{NETMOD_UDPGW_LISTEN} ' >/dev/null
printf 'UDPGW_SERVICE=active\\n'
printf 'UDPGW_LISTENER=yes\\n'
printf 'UDPGW_DNS_RESOLVER=yes\\n'
printf 'UDPGW_LISTEN={NETMOD_UDPGW_LISTEN}\\n'
"""


async def stage_netmod_udpgw(conn: Any) -> dict[str, str]:
    arch_result = await conn.run("uname -m", check=False, timeout=10)
    if int(getattr(arch_result, "exit_status", 1) or 0) != 0:
        detail = str(arch_result.stderr or arch_result.stdout or "uname failed").strip()
        raise RuntimeError(f"netmod_udpgw_remote_arch_failed:{detail[-500:]}")

    artifact, expected, arch = artifact_for_machine(str(arch_result.stdout or ""))
    remote = NETMOD_UDPGW_BINARY
    tmp = f"{remote}.tmp"

    prepare = await conn.run(
        f"install -d -m 0755 {shlex.quote(str(Path(remote).parent))}",
        check=False,
        timeout=15,
    )
    if int(getattr(prepare, "exit_status", 1) or 0) != 0:
        detail = str(prepare.stderr or prepare.stdout or "binary directory failed").strip()
        raise RuntimeError(f"netmod_udpgw_remote_dir_failed:{detail[-800:]}")

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
        raise RuntimeError(f"netmod_udpgw_remote_artifact_install_failed:{detail[-1200:]}")

    service = await conn.run(_service_install_script(), check=False, timeout=45)
    if int(getattr(service, "exit_status", 1) or 0) != 0:
        detail = str(service.stderr or service.stdout or "udpgw service failed").strip()
        raise RuntimeError(f"netmod_udpgw_service_install_failed:{detail[-1600:]}")

    return {
        "arch": arch,
        "sha256": expected,
        "artifact": artifact.name,
        "remote_path": remote,
        "service": NETMOD_UDPGW_SERVICE,
        "listen": NETMOD_UDPGW_LISTEN,
        "dns_resolver": "verified",
    }
