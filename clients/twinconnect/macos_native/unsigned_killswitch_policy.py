"""Native macOS PF Kill Switch policy, independent of the VPN engine.

This is a staging/validation component. No command in this module enables
or reloads the system firewall. A future privileged controller must own an
exclusive PF lease, observe the actual transport, and verify live recovery
before this policy can be exposed as enabled.
"""
from __future__ import annotations
from dataclasses import dataclass
import ipaddress
from pathlib import Path
import re
import subprocess
import tempfile

PFCTL = "/sbin/pfctl"
ANCHOR = "com.apple/twinconnect-killswitch"


@dataclass(frozen=True)
class Transport:
    """Exact outer transport endpoint attested by a privileged VPN worker."""
    ip: str
    port: int
    proto: str

    def __post_init__(self):
        if self.proto not in ("tcp", "udp") or type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("KS_TRANSPORT_INVALID")
        try:
            address = ipaddress.ip_address(self.ip)
        except ValueError:
            raise ValueError("KS_ENDPOINT_INVALID") from None
        if not address.is_global or "%" in self.ip:
            raise ValueError("KS_ENDPOINT_INVALID")
        object.__setattr__(self, "ip", str(address))


def render_policy(tunnel: str | None = None, uplink: str | None = None,
                  transports: tuple[Transport, ...] = ()) -> str:
    """Generate closed-by-default rules. Offline lock never permits uplink.

    A transport exception is restricted to an exact IP, port, protocol,
    interface and root-owned socket. No arbitrary DNS or LAN bypass.
    State is interface-bound so a previously allowed tunnel flow cannot
    continue on a physical interface following a route change. The tunnel
    itself uses no PF state. Never permit all utun/ppp interfaces.
    """
    if tunnel is None:
        if uplink is not None or transports:
            raise ValueError("KS_OFFLINE_EXCEPTIONS_REFUSED")
        return "pass quick on lo0 all no state\nblock drop quick all\n"
    if not re.fullmatch(r"(?:utun|ppp)[0-9]{1,4}", tunnel):
        raise ValueError("KS_TUNNEL_INTERFACE_INVALID")
    if not isinstance(uplink, str) or not re.fullmatch(r"en[0-9]{1,3}", uplink):
        raise ValueError("KS_UPLINK_INTERFACE_INVALID")
    if not 1 <= len(transports) <= 16 or any(not isinstance(t, Transport) for t in transports):
        raise ValueError("KS_TRANSPORT_UNATTESTED")
    rules = ["pass quick on lo0 all no state",
             f"pass quick on {tunnel} all no state"]
    for transport in sorted(set(transports), key=lambda t: (t.ip, t.proto, t.port)):
        family = "inet" if ipaddress.ip_address(transport.ip).version == 4 else "inet6"
        flags = " flags S/SA" if transport.proto == "tcp" else ""
        rules.append(f"pass out quick on {uplink} {family} proto {transport.proto} "
                     f"from any to {transport.ip} port = {transport.port} user = root"
                     f"{flags} keep state (if-bound)")
    rules.append("block drop quick all")
    return "\n".join(rules) + "\n"


def validate_kernel_syntax(rules: str) -> bool:
    """Ask Apple's real PF parser to validate, WITHOUT loading any rules."""
    with tempfile.TemporaryDirectory(prefix="twinconnect-ks-check-") as directory:
        path = Path(directory) / "rules.pf"
        path.write_text(rules, encoding="ascii")
        path.chmod(0o600)
        result = subprocess.run([PFCTL, "-n", "-a", ANCHOR, "-f", str(path)],
                                capture_output=True, timeout=10, check=False)
        return result.returncode == 0


if __name__ == "__main__":
    # Deliberately no public enable/disable command in the staging component.
    # Never let unprivileged UI declare a successful PF activation.
    import json
    import sys
    if sys.argv[1:] != ["--check"]:
        print(json.dumps({"state": "not_active", "reason": "KS_RUNTIME_NOT_VERIFIED"}))
        raise SystemExit(2)
    variants = (render_policy(), render_policy("utun15", "en0",
                (Transport("1.2.3.4", 443, "tcp"),
                 Transport("1.2.3.4", 51820, "udp"),
                 Transport("2606:4700:4700::1111", 443, "tcp"))),
                render_policy("ppp0", "en0", (Transport("1.2.3.4", 500, "udp"),
                                               Transport("1.2.3.4", 4500, "udp"))))
    passed = all(validate_kernel_syntax(rules) for rules in variants)
    print(json.dumps({"state": "syntax_validated_not_active" if passed else "syntax_rejected",
                      "variants": len(variants), "firewall_changed": False,
                      "leak_verified": False}))
    raise SystemExit(0 if passed else 1)
