from __future__ import annotations

import asyncio
import hashlib
import shlex
from pathlib import Path

from sqlalchemy.orm import Session

from ..tp2027_provision import ARTIFACTS, ARTIFACT_STORE
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
# TWINPANEL TP27 DIRECT TCP L3 V149
#
# Independent carrier lane for environments where the Iran-side UDP path is
# degraded or unavailable. This lane does not depend on TP2027 Backhaul, FoU,
# QUIC, KCP, ARQ, or the active TP27 GRE interface. It uses the already-vetted
# TwinPanel TCP TUN artifact directly between the Iran and Exit public IPs.
#
# The lane is intentionally a fallback, not a replacement for native GRE:
#   * TP27 Fast / native GRE remains the lowest-overhead fast path.
#   * Direct TCP is independently health-checked and benchmarked by SmartAuto.
#   * Multiple deterministic high TCP ports are tried only when installation
#     or full L3 qualification fails; occupied ports are skipped fail-closed.
#   * No TLS impersonation, packet mutation, or application-protocol spoofing
#     is introduced here; this is a plain independent L3 resilience lane.
# ============================================================

NAME = "tp27_tcp_direct"
MTU = 1320
LANES = 8
ARTIFACT_KEY = "tcp_2027"
REMOTE_BINARY = "/opt/twinpanel/transport/tp27-tcp-direct"
TCP_PORT_BASES = (46200, 47200, 48200)


def _port_candidates(tunnel_id: int) -> tuple[int, ...]:
    slot = int(tunnel_id) % 500
    return tuple(base + slot for base in TCP_PORT_BASES)


def _artifact() -> tuple[Path, str]:
    filename, expected = ARTIFACTS[ARTIFACT_KEY]
    path = ARTIFACT_STORE / filename

    if not path.is_file():
        raise RuntimeError(f"tp27_tcp_direct_artifact_missing:{path}")

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise RuntimeError(
            "tp27_tcp_direct_artifact_checksum_mismatch:"
            f"expected={expected}:actual={digest}"
        )

    return path, expected


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
ExecStart={REMOTE_BINARY} --mode server --tun {rt['interface']} --local {rt['exit_addr']} --listen :{int(port)} --lanes {LANES} --mtu {MTU}
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576

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
ExecStart={REMOTE_BINARY} --mode client --tun {rt['interface']} --local {rt['iran_addr']} --peer {exit_public}:{int(port)} --lanes {LANES} --mtu {MTU}
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576

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

    await asyncio.sleep(1.5)


async def install(tunnel_id: int, db: Session) -> dict:
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = dict(runtime(NAME, tunnel_id))
    rt["tunnel_id"] = int(tunnel_id)

    artifact_path, artifact_sha = _artifact()
    attempts: list[dict] = []

    mark(
        db,
        tunnel_id,
        NAME,
        status="installing",
        meta=str(
            {
                **rt,
                "generation": 149,
                "carrier_class": "direct-tcp-l3",
                "depends_on": None,
                "mtu": MTU,
                "lanes": LANES,
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
                    "generation": 149,
                    "carrier_class": "direct-tcp-l3",
                    "depends_on": None,
                    "selected_port": int(port),
                    "mtu": MTU,
                    "lanes": LANES,
                    "artifact_sha256": artifact_sha,
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
