#!/usr/bin/env python3
"""Minimal OpenConnect vpnc-script for a safe *unrouted* macOS TUN probe.

Unlike upstream vpnc-script, this helper NEVER changes default routes, DNS,
networksetup, pf, network services, or the en0 interface. OpenConnect
supplies the TUNDEV and INTERNAL_IP4_ADDRESS variables; only the utun
interface is configured. This is NOT a system-wide VPN.
"""
from __future__ import annotations

import ipaddress
import os
import re
import subprocess
import sys

IFCONFIG = "/sbin/ifconfig"
TUN_NAME = re.compile(r"utun[0-9]{1,3}\Z")


def validated_env(env: dict[str, str]) -> tuple[str, str, str, int]:
    reason = env.get("reason", "")
    if reason not in ("connect", "disconnect", "reconnect", "attempt-reconnect"):
        raise ValueError("CISCO_TUN_REASON_UNSUPPORTED")
    name = env.get("TUNDEV", "")
    if not TUN_NAME.fullmatch(name):
        raise ValueError("CISCO_TUN_INTERFACE_INVALID")
    address = env.get("INTERNAL_IP4_ADDRESS", "")
    try:
        ipv4 = ipaddress.IPv4Address(address)
        if ipv4.is_unspecified or ipv4.is_loopback or ipv4.is_multicast:
            raise ValueError
    except ValueError:
        raise ValueError("CISCO_TUN_ADDRESS_INVALID")
    raw_mtu = env.get("INTERNAL_IP4_MTU") or env.get("MTU") or "1300"
    if not raw_mtu.isdecimal() or not 576 <= int(raw_mtu) <= 9000:
        raise ValueError("CISCO_TUN_MTU_INVALID")
    return reason, name, str(ipv4), int(raw_mtu)


def execute(env: dict[str, str]) -> str:
    reason, name, address, mtu = validated_env(env)
    if reason in ("disconnect", "attempt-reconnect"):
        # Mac/OpenConnect owns the utun lifetime. Never delete a physical
        # address or network service, and don't modify routes or DNS.
        return "CISCO_UTUN_NO_SYSTEM_ROUTES"
    result = subprocess.run(
        [IFCONFIG, name, "inet", address, address,
         "netmask", "255.255.255.255", "mtu", str(mtu), "up"],
        capture_output=True, timeout=8, check=False)
    if result.returncode:
        raise ValueError("CISCO_UTUN_CONFIG_FAILED")
    return "CISCO_UTUN_CONFIGURED_UNROUTED"


def main() -> int:
    if sys.platform != "darwin" or os.geteuid() != 0:
        return 2
    try:
        execute(os.environ)
        return 0
    except (ValueError, OSError, subprocess.TimeoutExpired):
        # Do not log env, auth secrets, addresses or OpenConnect metadata.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
