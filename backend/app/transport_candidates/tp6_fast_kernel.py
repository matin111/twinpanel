from __future__ import annotations

import asyncio
import shlex

from .common import run
from .tp6_fast_contract import MTU, TXQUEUELEN
from .tp6_fast_ipv6 import canonical_ipv6


async def reset_pair(ci, ce, rt: dict) -> None:
    async def reset(conn, service: str) -> None:
        await conn.run(
            f"""
set +e
systemctl disable --now {shlex.quote(service)} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{shlex.quote(service)}
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1 || true
systemctl daemon-reload >/dev/null 2>&1 || true
true
""",
            check=False,
            timeout=45,
        )

    await asyncio.gather(
        reset(ci, rt["iran_service"]),
        reset(ce, rt["exit_service"]),
    )


async def install_peer(
    conn,
    *,
    role: str,
    service: str,
    interface: str,
    local_ipv6: str,
    remote_ipv6: str,
    local_addr: str,
    carrier_key: int,
    profile: str,
) -> None:
    local6 = canonical_ipv6(local_ipv6)
    remote6 = canonical_ipv6(remote_ipv6)

    if profile == "ip6gre":
        module = "ip6_gre"
        create = (
            f"ip link add {shlex.quote(interface)} type ip6gre "
            f"local {shlex.quote(local6)} remote {shlex.quote(remote6)} "
            f"key {int(carrier_key)} hoplimit 64"
        )
    elif profile == "ipip6":
        module = "ip6_tunnel"
        create = (
            f"ip -6 tunnel add {shlex.quote(interface)} mode ipip6 "
            f"local {shlex.quote(local6)} remote {shlex.quote(remote6)} hoplimit 64"
        )
    else:
        raise RuntimeError("tp6_unknown_profile")

    start_script = "; ".join(
        [
            "set -e",
            f"modprobe {shlex.quote(module)} >/dev/null 2>&1 || true",
            f"ip link del {shlex.quote(interface)} >/dev/null 2>&1 || true",
            create,
            f"ip addr add {shlex.quote(local_addr)} dev {shlex.quote(interface)}",
            f"ip link set dev {shlex.quote(interface)} mtu {MTU} txqueuelen {TXQUEUELEN} up",
        ]
    )
    stop_script = f"ip link del {shlex.quote(interface)} >/dev/null 2>&1 || true"

    unit = f"""[Unit]
Description=TwinPanel TP6 Fast {role} ({profile})
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c {shlex.quote(start_script)}
ExecStop=/bin/bash -c {shlex.quote(stop_script)}

[Install]
WantedBy=multi-user.target
"""

    await run(
        conn,
        f"""
set -e
cat > /etc/systemd/system/{shlex.quote(service)} <<'EOF'
{unit}EOF
systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}
""",
        f"tp6_{profile}_{role}_install",
        90,
    )


async def install_profile(
    ci,
    ce,
    *,
    rt: dict,
    iran_ipv6: str,
    exit_ipv6: str,
    carrier_key: int,
    profile: str,
) -> None:
    await reset_pair(ci, ce, rt)
    await asyncio.gather(
        install_peer(
            ci,
            role="iran",
            service=rt["iran_service"],
            interface=rt["interface"],
            local_ipv6=iran_ipv6,
            remote_ipv6=exit_ipv6,
            local_addr=rt["iran_addr"],
            carrier_key=carrier_key,
            profile=profile,
        ),
        install_peer(
            ce,
            role="exit",
            service=rt["exit_service"],
            interface=rt["interface"],
            local_ipv6=exit_ipv6,
            remote_ipv6=iran_ipv6,
            local_addr=rt["exit_addr"],
            carrier_key=carrier_key,
            profile=profile,
        ),
    )
    await asyncio.sleep(1.5)
