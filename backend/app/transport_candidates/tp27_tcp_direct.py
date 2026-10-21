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
# TWINPANEL TP27 DIRECT TCP L3 V152
#
# Independent non-UDP carrier built from source inside the verified TwinPanel
# release. V149 referenced a controller-local TP2027 artifact that is not part
# of prebuilt releases, so production could never install this lane on a clean
# controller. V152 packages its own deterministic Go carrier + SHA256 sidecar.
#
# Data-plane properties:
#   * independent from GRE/FoU/MASQUE/TP2027 Backhaul
#   * 8 parallel TCP lanes with stable per-flow hashing
#   * source-restricted Exit firewall ports
#   * per-tunnel root-only shared token before lane admission
#   * reconnecting client lanes and TCP_NODELAY/keepalive
#   * full shared candidate probe + SmartAuto throughput qualification
# ============================================================

NAME = "tp27_tcp_direct"
MTU = 1320
LANES = 8
REMOTE_BINARY = "/opt/twinpanel/transport/tp27-tcp-direct"
TCP_PORT_BASES = (46200, 47200, 48200)
ARTIFACT_NAME = "tp27-tcp-direct-linux-x86_64"


def _port_candidates(tunnel_id: int) -> tuple[int, ...]:
    slot = int(tunnel_id) % 500
    return tuple(base + slot for base in TCP_PORT_BASES)


def _artifact() -> tuple[Path, str]:
    backend_dir = Path(__file__).resolve().parents[2]
    artifact = backend_dir / "artifacts" / ARTIFACT_NAME
    sidecar = backend_dir / "artifacts" / f"{ARTIFACT_NAME}.sha256"

    if not artifact.is_file():
        raise RuntimeError(f"tp27_tcp_direct_artifact_missing:{artifact}")
    if not sidecar.is_file():
        raise RuntimeError(f"tp27_tcp_direct_checksum_missing:{sidecar}")

    expected = sidecar.read_text(encoding="utf-8").strip().split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise RuntimeError("tp27_tcp_direct_checksum_invalid")

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if digest != expected:
        raise RuntimeError(
            "tp27_tcp_direct_artifact_checksum_mismatch:"
            f"expected={expected}:actual={digest}"
        )

    return artifact, expected


def _token_path(tunnel_id: int) -> str:
    return f"/etc/twinpanel/tcp-direct/tunnel-{int(tunnel_id)}.token"


async def _write_token(conn, path: str, value: str) -> None:
    payload = base64.b64encode(value.encode("utf-8")).decode("ascii")
    await run(
        conn,
        f"""
set -e
install -d -m 0700 /etc/twinpanel/tcp-direct
printf %s {shlex.quote(payload)} | base64 -d > {shlex.quote(path)}
chmod 0600 {shlex.quote(path)}
""",
        "tp27_tcp_direct_token_write",
        15,
    )


async def _reset_pair(ci, ce, rt: dict, iran_public: str) -> None:
    comment = f"TwinPanel-TP27-TCP-{int(rt['tunnel_id'])}"

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
  for p in {' '.join(str(p) for p in _port_candidates(int(rt['tunnel_id'])))}; do
    while iptables -C INPUT -p tcp --dport "$p" -s {shlex.quote(iran_public)} \
      -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null; do
      iptables -D INPUT -p tcp --dport "$p" -s {shlex.quote(iran_public)} \
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
) -> None:
    comment = f"TwinPanel-TP27-TCP-{int(tunnel_id)}"

    port_check = await ce.run(
        f"ss -H -ltn 'sport = :{int(port)}' 2>/dev/null | grep -q .",
        check=False,
        timeout=10,
    )
    if port_check.exit_status == 0:
        raise RuntimeError(f"tp27_tcp_direct_port_busy:{int(port)}")

    exit_unit = f"""[Unit]
Description=TwinPanel TP27 Direct TCP {int(tunnel_id)} Exit
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
ExecStart={REMOTE_BINARY} --mode server --tun {rt['interface']} --local {rt['exit_addr']} --listen :{int(port)} --lanes {LANES} --mtu {MTU} --token-file {token_path}
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
Description=TwinPanel TP27 Direct TCP {int(tunnel_id)} Iran
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
ExecStart={REMOTE_BINARY} --mode client --tun {rt['interface']} --local {rt['iran_addr']} --peer {exit_public}:{int(port)} --lanes {LANES} --mtu {MTU} --token-file {token_path}
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
  iptables -C INPUT -p tcp --dport {int(port)} -s {shlex.quote(iran_public)} \
    -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -p tcp --dport {int(port)} -s {shlex.quote(iran_public)} \
    -m comment --comment {shlex.quote(comment)} -j ACCEPT
fi
cat > /etc/systemd/system/{shlex.quote(rt['exit_service'])} <<'EOF'
{exit_unit}EOF
systemctl daemon-reload
systemctl enable {shlex.quote(rt['exit_service'])} >/dev/null
systemctl restart {shlex.quote(rt['exit_service'])}
""",
        "tp27_tcp_direct_exit_install",
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
        "tp27_tcp_direct_iran_install",
        45,
    )

    await asyncio.sleep(2.0)


async def install(tunnel_id: int, db: Session) -> dict:
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = dict(runtime(NAME, tunnel_id))
    rt["tunnel_id"] = int(tunnel_id)

    artifact_path, artifact_sha = _artifact()
    token = secrets.token_urlsafe(36)
    token_path = _token_path(tunnel_id)
    attempts: list[dict] = []

    mark(
        db,
        tunnel_id,
        NAME,
        status="installing",
        meta=str(
            {
                **rt,
                "generation": 152,
                "carrier_class": "direct-tcp-l3",
                "depends_on": None,
                "mtu": MTU,
                "lanes": LANES,
                "artifact_sha256": artifact_sha,
                "port_candidates": list(_port_candidates(tunnel_id)),
                "source_built": True,
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
            _write_token(ci, token_path, token),
            _write_token(ce, token_path, token),
        )

        for port in _port_candidates(tunnel_id):
            try:
                await _reset_pair(
                    ci,
                    ce,
                    rt,
                    str(iran.public_ip),
                )
                await _install_profile(
                    ci,
                    ce,
                    tunnel_id=int(tunnel_id),
                    iran_public=str(iran.public_ip),
                    exit_public=str(exit_node.public_ip),
                    rt=rt,
                    port=int(port),
                    token_path=token_path,
                )
                health = await probe(
                    ci,
                    ce,
                    name=NAME,
                    tunnel_id=int(tunnel_id),
                    rt=rt,
                )

                attempts.append(
                    {
                        "port": int(port),
                        "result": "online",
                    }
                )

                meta = {
                    **rt,
                    **health,
                    "generation": 152,
                    "carrier_class": "direct-tcp-l3",
                    "depends_on": None,
                    "selected_port": int(port),
                    "mtu": MTU,
                    "lanes": LANES,
                    "artifact_sha256": artifact_sha,
                    "source_built": True,
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

        await _reset_pair(
            ci,
            ce,
            rt,
            str(iran.public_ip),
        )
        raise RuntimeError(f"tp27_tcp_direct_all_ports_failed:{attempts!r}")

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
