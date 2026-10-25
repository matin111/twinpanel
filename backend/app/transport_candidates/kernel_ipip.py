from __future__ import annotations

import asyncio
import json
import shlex

from sqlalchemy.orm import Session

from . import common


NAME = "kernel_ipip"
MTU = 1400


def _helper_path(tunnel_id: int, role: str) -> str:
    return f"/usr/local/sbin/twinpanel-kernel-ipip-{int(tunnel_id)}-{role}"


async def _install_peer(
    conn,
    *,
    tunnel_id: int,
    role: str,
    local_public: str,
    remote_public: str,
    local_addr: str,
    interface: str,
    service: str,
) -> None:
    helper = _helper_path(tunnel_id, role)
    comment = f"TwinPanel-IPIP-{int(tunnel_id)}-{role}"

    script = f"""#!/usr/bin/env bash
set -euo pipefail
ACTION="${{1:-start}}"
IFACE={shlex.quote(interface)}
LOCAL={shlex.quote(local_public)}
REMOTE={shlex.quote(remote_public)}
ADDR={shlex.quote(local_addr)}
COMMENT={shlex.quote(comment)}

remove_firewall() {{
  if command -v iptables >/dev/null 2>&1; then
    while iptables -C INPUT -p 4 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT >/dev/null 2>&1; do
      iptables -D INPUT -p 4 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT || break
    done
  fi
}}

stop_runtime() {{
  ip link del "$IFACE" >/dev/null 2>&1 || true
  remove_firewall
}}

if [[ "$ACTION" == "stop" ]]; then
  stop_runtime
  exit 0
fi

modprobe ipip >/dev/null 2>&1 || true
stop_runtime

if command -v iptables >/dev/null 2>&1; then
  iptables -I INPUT -p 4 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT
fi

ip tunnel add "$IFACE" mode ipip local "$LOCAL" remote "$REMOTE" ttl 255
ip addr replace "$ADDR" dev "$IFACE"
ip link set dev "$IFACE" mtu {MTU} up
"""

    unit = f"""[Unit]
Description=TwinPanel Kernel IPIP Tunnel {int(tunnel_id)} {role}
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={helper} start
ExecStop={helper} stop
TimeoutStartSec=30
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
"""

    await common.run(
        conn,
        f"""
set -e
cat > {shlex.quote(helper)} <<'TPIP_HELPER'
{script}TPIP_HELPER
chmod 0755 {shlex.quote(helper)}
cat > /etc/systemd/system/{shlex.quote(service)} <<'TPIP_UNIT'
{unit}TPIP_UNIT
systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}
""",
        f"kernel_ipip_{role}_install",
        90,
    )


async def install(tunnel_id: int, db: Session) -> dict:
    _, iran, exit_node = common.tunnel_nodes(db, tunnel_id)
    rt = common.runtime(NAME, tunnel_id)

    common.mark(
        db,
        tunnel_id,
        NAME,
        status="installing",
        meta=json.dumps(
            {
                **rt,
                "source": "linux-kernel",
                "outer_family": "ipv4",
                "encapsulation": "ipip",
                "ip_protocol": 4,
                "mtu": MTU,
                "encrypted": False,
                "install_mode": "explicit",
            },
            sort_keys=True,
        ),
    )

    ci = ce = None
    try:
        ci, ce = await common.connect_pair(iran, exit_node, db)
        await asyncio.gather(common.prerequisites(ci), common.prerequisites(ce))

        iran_route, exit_route = await asyncio.gather(
            common.run(
                ci,
                f"ip -4 route get {shlex.quote(str(exit_node.public_ip))}",
                "kernel_ipip_iran_peer_route",
                20,
            ),
            common.run(
                ce,
                f"ip -4 route get {shlex.quote(str(iran.public_ip))}",
                "kernel_ipip_exit_peer_route",
                20,
            ),
        )

        await asyncio.gather(
            _install_peer(
                ci,
                tunnel_id=tunnel_id,
                role="iran",
                local_public=str(iran.public_ip),
                remote_public=str(exit_node.public_ip),
                local_addr=rt["iran_addr"],
                interface=rt["interface"],
                service=rt["iran_service"],
            ),
            _install_peer(
                ce,
                tunnel_id=tunnel_id,
                role="exit",
                local_public=str(exit_node.public_ip),
                remote_public=str(iran.public_ip),
                local_addr=rt["exit_addr"],
                interface=rt["interface"],
                service=rt["exit_service"],
            ),
        )

        health = await common.probe(
            ci,
            ce,
            name=NAME,
            tunnel_id=tunnel_id,
            rt=rt,
        )

        metadata = {
            **rt,
            **health,
            "source": "linux-kernel",
            "outer_family": "ipv4",
            "encapsulation": "ipip",
            "ip_protocol": 4,
            "mtu": MTU,
            "encrypted": False,
            "install_mode": "explicit",
            "iran_peer_route": iran_route[-1500:],
            "exit_peer_route": exit_route[-1500:],
        }
        common.mark(
            db,
            tunnel_id,
            NAME,
            status="online",
            latency_ms=health["latency_ms"],
            meta=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        )
        return {
            "ok": True,
            "transport": NAME,
            "runtime": rt,
            "probe": health,
        }

    except Exception as exc:
        iran_diag = (
            await common.diag(ci, rt["iran_service"], rt["interface"])
            if ci
            else ""
        )
        exit_diag = (
            await common.diag(ce, rt["exit_service"], rt["interface"])
            if ce
            else ""
        )
        message = (
            f"{type(exc).__name__}: {exc} | "
            f"iran={iran_diag[-1800:]} | exit={exit_diag[-1800:]}"
        )
        common.mark(db, tunnel_id, NAME, status="failed", error=message)
        raise RuntimeError(message) from exc
    finally:
        await common.close_pair(ci, ce)
