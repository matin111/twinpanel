from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import secrets
import shlex
from pathlib import Path

from sqlalchemy.orm import Session

from .common import (
    close_pair,
    connect_pair,
    copy_binary,
    diag,
    mark,
    prerequisites,
    probe,
    run,
    runtime,
    tunnel_nodes,
)


# ============================================================
# TWINPANEL TP27 MASQUE CONNECT-IP L3 V151
#
# Independent standards-based L3 carrier:
#   * RFC 9484 CONNECT-IP over HTTP/3 / QUIC datagrams
#   * independent from TP27 Fast, FoU and TP27 Direct TCP
#   * TLS 1.3 with leaf-certificate SHA-256 pinning
#   * per-tunnel bearer token, stored root-only on both nodes
#   * SmartAuto full dataplane qualification + throughput benchmark
#
# This lane is intentionally UDP-dependent. It is never forced when the Iran
# UDP path is degraded; TP27 Direct TCP remains the independent non-UDP lane.
# ============================================================

NAME = "tp27_masque"
MTU = 1280
REMOTE_BINARY = "/opt/twinpanel/transport/tp27-masque"
UDP_PORT_BASES = (28400, 29400, 30400)
ARTIFACT_NAME = "tp27-masque-linux-x86_64"


def _port_candidates(tunnel_id: int) -> tuple[int, ...]:
    slot = int(tunnel_id) % 500
    return tuple(base + slot for base in UDP_PORT_BASES)


def _artifact() -> tuple[Path, str]:
    backend_dir = Path(__file__).resolve().parents[2]
    artifact = backend_dir / "artifacts" / ARTIFACT_NAME
    sidecar = backend_dir / "artifacts" / f"{ARTIFACT_NAME}.sha256"

    if not artifact.is_file():
        raise RuntimeError(f"tp27_masque_artifact_missing:{artifact}")
    if not sidecar.is_file():
        raise RuntimeError(f"tp27_masque_checksum_missing:{sidecar}")

    expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError("tp27_masque_checksum_invalid")

    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError(
            "tp27_masque_artifact_checksum_mismatch:"
            f"expected={expected}:actual={actual}"
        )

    return artifact, expected


def _secret_paths(tunnel_id: int) -> tuple[str, str, str]:
    tid = int(tunnel_id)
    base = "/etc/twinpanel/masque"
    return (
        f"{base}/tunnel-{tid}.token",
        f"{base}/tunnel-{tid}.crt",
        f"{base}/tunnel-{tid}.key",
    )


async def _write_secret(conn, path: str, value: str) -> None:
    payload = base64.b64encode(value.encode("utf-8")).decode("ascii")
    await run(
        conn,
        f"""
set -e
install -d -m 0700 /etc/twinpanel/masque
printf %s {shlex.quote(payload)} | base64 -d > {shlex.quote(path)}
chmod 0600 {shlex.quote(path)}
""",
        "tp27_masque_secret_write",
        15,
    )


async def _certificate_fingerprint(ce, cert_path: str, key_path: str) -> str:
    # transport_candidates.common.run() deliberately returns normalized stdout
    # as a plain string. V151 incorrectly treated that string like an AsyncSSH
    # result object (`result.stdout`), so installation failed before either
    # systemd unit was created. Keep the shared run() contract unchanged and
    # parse its returned text directly.
    output = await run(
        ce,
        f"""
set -e
install -d -m 0700 /etc/twinpanel/masque
if [ ! -s {shlex.quote(cert_path)} ] || [ ! -s {shlex.quote(key_path)} ]; then
  rm -f {shlex.quote(cert_path)} {shlex.quote(key_path)}
  openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \
    -subj '/CN=tp27-masque.invalid' \
    -keyout {shlex.quote(key_path)} \
    -out {shlex.quote(cert_path)} >/dev/null 2>&1
  chmod 0600 {shlex.quote(key_path)}
  chmod 0644 {shlex.quote(cert_path)}
fi
openssl x509 -in {shlex.quote(cert_path)} -outform DER | sha256sum | awk '{{print $1}}'
""",
        "tp27_masque_certificate",
        30,
    )
    lines = str(output or "").strip().splitlines()
    value = lines[-1].strip().lower() if lines else ""
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise RuntimeError("tp27_masque_certificate_fingerprint_invalid")
    return value


async def _reset_pair(ci, ce, rt: dict, iran_public: str) -> None:
    comment = f"TwinPanel-TP27-MASQUE-{int(rt['tunnel_id'])}"
    ports = " ".join(str(p) for p in _port_candidates(int(rt["tunnel_id"])))

    await asyncio.gather(
        ci.run(
            f"""
set +e
systemctl disable --now {shlex.quote(rt['iran_service'])} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{shlex.quote(rt['iran_service'])}
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1 || true
systemctl daemon-reload >/dev/null 2>&1 || true
true
""",
            check=False,
        ),
        ce.run(
            f"""
set +e
systemctl disable --now {shlex.quote(rt['exit_service'])} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{shlex.quote(rt['exit_service'])}
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1 || true
if command -v iptables >/dev/null 2>&1; then
  for p in {ports}; do
    while iptables -C INPUT -p udp --dport "$p" -s {shlex.quote(iran_public)} \
      -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null; do
      iptables -D INPUT -p udp --dport "$p" -s {shlex.quote(iran_public)} \
        -m comment --comment {shlex.quote(comment)} -j ACCEPT || break
    done
  done
fi
systemctl daemon-reload >/dev/null 2>&1 || true
true
""",
            check=False,
        ),
    )


async def _install_profile(
    ci,
    ce,
    *,
    tunnel_id: int,
    iran_public: str,
    exit_public: str,
    rt: dict,
    port: int,
    token_path: str,
    cert_path: str,
    key_path: str,
    cert_pin: str,
) -> None:
    comment = f"TwinPanel-TP27-MASQUE-{int(tunnel_id)}"

    port_check = await ce.run(
        f"ss -H -lun 'sport = :{int(port)}' 2>/dev/null | grep -q .",
        check=False,
        timeout=10,
    )
    if port_check.exit_status == 0:
        raise RuntimeError(f"tp27_masque_port_busy:{int(port)}")

    exit_unit = f"""[Unit]
Description=TwinPanel TP27 MASQUE H3 {int(tunnel_id)} Exit
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
ExecStart={REMOTE_BINARY} --mode server --tun {rt['interface']} --local {rt['exit_addr']} --listen 0.0.0.0:{int(port)} --cert {cert_path} --key {key_path} --token-file {token_path} --mtu {MTU}
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_ADMIN
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""

    iran_unit = f"""[Unit]
Description=TwinPanel TP27 MASQUE H3 {int(tunnel_id)} Iran
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
ExecStart={REMOTE_BINARY} --mode client --tun {rt['interface']} --local {rt['iran_addr']} --peer {exit_public}:{int(port)} --token-file {token_path} --pin-sha256 {cert_pin} --mtu {MTU}
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_ADMIN
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""

    await run(
        ce,
        f"""
set -e
install -d -m 0755 /opt/twinpanel/transport
if command -v iptables >/dev/null 2>&1; then
  iptables -C INPUT -p udp --dport {int(port)} -s {shlex.quote(iran_public)} \
    -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -p udp --dport {int(port)} -s {shlex.quote(iran_public)} \
    -m comment --comment {shlex.quote(comment)} -j ACCEPT
fi
cat > /etc/systemd/system/{shlex.quote(rt['exit_service'])} <<'EOF'
{exit_unit}EOF
systemctl daemon-reload
systemctl enable {shlex.quote(rt['exit_service'])} >/dev/null
systemctl restart {shlex.quote(rt['exit_service'])}
""",
        "tp27_masque_exit_install",
        45,
    )

    await asyncio.sleep(0.8)

    await run(
        ci,
        f"""
set -e
install -d -m 0755 /opt/twinpanel/transport
cat > /etc/systemd/system/{shlex.quote(rt['iran_service'])} <<'EOF'
{iran_unit}EOF
systemctl daemon-reload
systemctl enable {shlex.quote(rt['iran_service'])} >/dev/null
systemctl restart {shlex.quote(rt['iran_service'])}
""",
        "tp27_masque_iran_install",
        45,
    )

    await asyncio.sleep(2.0)


async def install(tunnel_id: int, db: Session) -> dict:
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = dict(runtime(NAME, tunnel_id))
    rt["tunnel_id"] = int(tunnel_id)

    artifact_path, artifact_sha = _artifact()
    token = secrets.token_urlsafe(36)
    token_path, cert_path, key_path = _secret_paths(tunnel_id)
    attempts: list[dict] = []

    mark(
        db,
        tunnel_id,
        NAME,
        status="installing",
        meta=str(
            {
                **rt,
                "generation": 151,
                "carrier_class": "masque-connect-ip-h3",
                "depends_on": None,
                "udp_dependency": True,
                "mtu": MTU,
                "artifact_sha256": artifact_sha,
                "port_candidates": list(_port_candidates(tunnel_id)),
            }
        ),
    )

    ci = ce = None

    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))

        await asyncio.gather(
            copy_binary(ci, str(artifact_path), REMOTE_BINARY),
            copy_binary(ce, str(artifact_path), REMOTE_BINARY),
        )

        await asyncio.gather(
            _write_secret(ci, token_path, token),
            _write_secret(ce, token_path, token),
        )
        cert_pin = await _certificate_fingerprint(ce, cert_path, key_path)

        for port in _port_candidates(tunnel_id):
            try:
                await _reset_pair(ci, ce, rt, str(iran.public_ip))
                await _install_profile(
                    ci,
                    ce,
                    tunnel_id=int(tunnel_id),
                    iran_public=str(iran.public_ip),
                    exit_public=str(exit_node.public_ip),
                    rt=rt,
                    port=int(port),
                    token_path=token_path,
                    cert_path=cert_path,
                    key_path=key_path,
                    cert_pin=cert_pin,
                )

                health = await probe(
                    ci,
                    ce,
                    name=NAME,
                    tunnel_id=int(tunnel_id),
                    rt=rt,
                )
                if not (
                    health.get("peer_ping")
                    and health.get("tcp_egress")
                    and health.get("udp_egress")
                ):
                    raise RuntimeError(
                        f"tp27_masque_full_dataplane_probe_failed:{health!r}"
                    )

                attempts.append({"port": int(port), "result": "online"})
                meta = {
                    **rt,
                    **health,
                    "generation": 151,
                    "carrier_class": "masque-connect-ip-h3",
                    "depends_on": None,
                    "udp_dependency": True,
                    "selected_port": int(port),
                    "mtu": MTU,
                    "artifact_sha256": artifact_sha,
                    "cert_pin_sha256": cert_pin,
                    "attempts": attempts,
                }
                mark(
                    db,
                    tunnel_id,
                    NAME,
                    status="online",
                    latency_ms=health["latency_ms"],
                    meta=str(meta),
                )
                return {
                    "ok": True,
                    "transport": NAME,
                    "runtime": rt,
                    "port": int(port),
                    "probe": health,
                }

            except Exception as exc:
                attempts.append(
                    {
                        "port": int(port),
                        "result": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        await _reset_pair(ci, ce, rt, str(iran.public_ip))
        raise RuntimeError(f"tp27_masque_all_ports_failed:{attempts!r}")

    except Exception as exc:
        a = await diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        message = (
            f"{type(exc).__name__}: {exc} | "
            f"iran={a[-1800:]} | exit={b[-1800:]}"
        )
        mark(db, tunnel_id, NAME, status="failed", error=message)
        raise RuntimeError(message) from exc

    finally:
        await close_pair(ci, ce)
