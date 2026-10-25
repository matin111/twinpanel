from __future__ import annotations

import asyncio
import json
import shlex

from sqlalchemy.orm import Session

from . import common
from .kernel_cleanup_v210 import cleanup_probe_state


NAME = "kernel_vxlan"
MTU = 1360


def _helper_path(tunnel_id: int, role: str) -> str:
    return f"/usr/local/sbin/twinpanel-kernel-vxlan-{int(tunnel_id)}-{role}"


def _vni(tunnel_id: int) -> int:
    return 10000 + (int(tunnel_id) % 60000)


async def _best_effort_stop(
    conn,
    *,
    service: str,
    interface: str,
    helper: str,
) -> None:
    if conn is None:
        return
    try:
        unit_path = f"/etc/systemd/system/{service}"
        await conn.run(
            f"""
set +e
systemctl disable --now {shlex.quote(service)} >/dev/null 2>&1 || true
if [ -x {shlex.quote(helper)} ]; then
  {shlex.quote(helper)} stop >/dev/null 2>&1 || true
fi
ip link del {shlex.quote(interface)} >/dev/null 2>&1 || true
rm -f {shlex.quote(unit_path)} {shlex.quote(helper)}
systemctl daemon-reload >/dev/null 2>&1 || true
true
""",
            check=False,
            timeout=30,
        )
    except Exception:
        pass


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
    port: int,
    public_interface: str,
    vni: int,
) -> None:
    helper = _helper_path(tunnel_id, role)
    comment = f"TwinPanel-VXLAN-{int(tunnel_id)}-{role}"

    script = f"""#!/usr/bin/env bash
set -euo pipefail
ACTION="${{1:-start}}"
IFACE={shlex.quote(interface)}
PUBLIC_IF={shlex.quote(public_interface)}
LOCAL={shlex.quote(local_public)}
REMOTE={shlex.quote(remote_public)}
ADDR={shlex.quote(local_addr)}
PORT={int(port)}
VNI={int(vni)}
COMMENT={shlex.quote(comment)}

remove_firewall() {{
  if command -v iptables >/dev/null 2>&1; then
    while iptables -C INPUT -p udp --dport "$PORT" -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT >/dev/null 2>&1; do
      iptables -D INPUT -p udp --dport "$PORT" -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT || break
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

modprobe vxlan >/dev/null 2>&1 || true
stop_runtime

if command -v iptables >/dev/null 2>&1; then
  iptables -I INPUT -p udp --dport "$PORT" -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT
fi

ip link add "$IFACE" type vxlan \
  id "$VNI" \
  local "$LOCAL" \
  remote "$REMOTE" \
  dstport "$PORT" \
  dev "$PUBLIC_IF" \
  ttl 64
ip addr replace "$ADDR" dev "$IFACE"
ip link set dev "$IFACE" mtu {MTU} up
"""

    unit = f"""[Unit]
Description=TwinPanel Kernel VXLAN Tunnel {int(tunnel_id)} {role}
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
cat > {shlex.quote(helper)} <<'TPVX_HELPER'
{script}TPVX_HELPER
chmod 0755 {shlex.quote(helper)}
cat > /etc/systemd/system/{shlex.quote(service)} <<'TPVX_UNIT'
{unit}TPVX_UNIT
systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}
""",
        f"kernel_vxlan_{role}_install",
        90,
    )


async def install(tunnel_id: int, db: Session) -> dict:
    _, iran, exit_node = common.tunnel_nodes(db, tunnel_id)
    rt = common.runtime(NAME, tunnel_id)
    if rt.get("port") is None:
        raise RuntimeError("kernel_vxlan_port_missing")

    port = int(rt["port"])
    vni = _vni(tunnel_id)

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
                "encapsulation": "vxlan",
                "udp_port": port,
                "vni": vni,
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

        iran_public_if, exit_public_if = await asyncio.gather(
            common.default_interface(ci),
            common.default_interface(ce),
        )

        iran_route, exit_route = await asyncio.gather(
            common.run(
                ci,
                f"ip -4 route get {shlex.quote(str(exit_node.public_ip))}",
                "kernel_vxlan_iran_peer_route",
                20,
            ),
            common.run(
                ce,
                f"ip -4 route get {shlex.quote(str(iran.public_ip))}",
                "kernel_vxlan_exit_peer_route",
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
                port=port,
                public_interface=iran_public_if,
                vni=vni,
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
                port=port,
                public_interface=exit_public_if,
                vni=vni,
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
            "encapsulation": "vxlan",
            "udp_port": port,
            "vni": vni,
            "mtu": MTU,
            "encrypted": False,
            "install_mode": "explicit",
            "iran_public_interface": iran_public_if,
            "exit_public_interface": exit_public_if,
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

        await asyncio.gather(
            _best_effort_stop(
                ci,
                service=rt["iran_service"],
                interface=rt["interface"],
                helper=_helper_path(tunnel_id, "iran"),
            ),
            _best_effort_stop(
                ce,
                service=rt["exit_service"],
                interface=rt["interface"],
                helper=_helper_path(tunnel_id, "exit"),
            ),
        )

        cleanup_errors = await cleanup_probe_state(
            ci,
            ce,
            name=NAME,
            tunnel_id=tunnel_id,
            rt=rt,
        )
        cleanup_detail = "ok" if not cleanup_errors else ";".join(cleanup_errors)

        message = (
            f"{type(exc).__name__}: {exc} | "
            f"iran={iran_diag[-1800:]} | exit={exit_diag[-1800:]} | "
            f"cleanup={cleanup_detail}"
        )
        common.mark(db, tunnel_id, NAME, status="failed", error=message)
        raise RuntimeError(message) from exc
    finally:
        await common.close_pair(ci, ce)
