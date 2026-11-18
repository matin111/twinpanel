"""Prepare a Rakhsh-compatible three-carrier *plan*, never activate it.

Rakhsh LINKS.md: one tunnel between two endpoints can use one primary carrier
and multiple [[link]] carriers. Its lane count is independent of link count.
The generated arguments are a reviewable staging plan, NOT a running service.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

ALLOWED = frozenset({"tcp", "tls", "ws", "wss", "quic", "quicv2", "kcp"})
UDP = frozenset({"quic", "quicv2", "kcp"})
DEFAULT_LINKS = (("wss", 17443), ("quicv2", 17443), ("kcp", 17001))


@dataclass(frozen=True)
class Carrier:
    name: str
    port: int

    def validate(self) -> None:
        if self.name not in ALLOWED:
            raise ValueError("Unsupported carrier")
        if not isinstance(self.port, int) or isinstance(self.port, bool) or not (1024 <= self.port <= 65535):
            raise ValueError("Carrier port must be in 1024..65535")

    @property
    def socket_protocol(self) -> str:
        return "udp" if self.name in UDP else "tcp"


def validate_links(links: tuple[Carrier, ...]) -> tuple[Carrier, ...]:
    if len(links) != 3:
        raise ValueError("Exactly three independently selectable transport links required")
    seen = set()
    for carrier in links:
        carrier.validate()
        key = (carrier.socket_protocol, carrier.port)
        if key in seen:
            raise ValueError("Two links cannot bind the same protocol and port")
        seen.add(key)
    return links


def init_args(exit_ip: str, links: tuple[Carrier, ...], *, lanes: int = 4) -> list[str]:
    """Produce only argv, no process execution, firewall changes or credentials.

    Rakhsh 'init' generates matching keys/configs; NEVER hand-roll them. Run
    only in a separate operational deployment with real remote port checks.
    """
    validate_links(links)
    if not 1 <= lanes <= 16:
        raise ValueError("lanes must be between 1 and 16")
    try:
        ip = ipaddress.ip_address(exit_ip)
    except ValueError as exc:
        raise ValueError("Use a numeric peer IP for the initial plan") from exc
    if ip.is_unspecified or ip.is_multicast or ip.is_loopback:
        raise ValueError("Peer must be a routable address")
    host = f"[{ip}]" if ip.version == 6 else str(ip)
    first, *additional = links
    argv = ["rakhsh", "init", "--tunnel-addr", f"{host}:{first.port}",
            "--carrier", first.name, "--resume"]
    for link in additional:
        spec = link.name if link.port == first.port else f"{link.name}:{link.port}"
        argv.extend(["--link", spec])
    return argv


def planned_status() -> dict:
    return {
        "carrier_plan": [{"carrier": c, "port": p} for c, p in DEFAULT_LINKS],
        "carrier_count": 3,
        "carrier_state": "not_installed",
        "traffic_activated": False,
        "warning": "Rakhsh carrier configs, listeners, authentication and failover have not been deployed",
    }
