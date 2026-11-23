#!/usr/bin/env python3
"""Minimal OpenConnect vpnc-script for a safe *unrouted* macOS TUN probe.

Unlike upstream vpnc-script, this helper NEVER changes default routes, DNS,
networksetup, pf, network services, or the en0 interface. OpenConnect
supplies the TUNDEV and INTERNAL_IP4_ADDRESS variables; only the utun
interface is configured. This is NOT a system-wide VPN.
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

IFCONFIG = "/sbin/ifconfig"
TUN_NAME = re.compile(r"utun[0-9]{1,3}\Z")
DNS_STATE = Path("/private/var/run/twinconnect-cisco-route-guard/tunnel-dns.json")


def tunnel_dns(env: dict[str, str]) -> list[str]:
    """Take only legitimate IPv4 DNS values OpenConnect supplies, no secrets."""
    raw = [env.get("INTERNAL_IP4_DNS", "")]
    raw.extend(env.get("INTERNAL_IP4_DNS" + str(i), "") for i in range(1, 5))
    addresses: list[str] = []
    for field in raw:
        for token in re.split(r"[\s,;]+", field.strip()):
            if not token:
                continue
            try:
                parsed = ipaddress.IPv4Address(token)
                if parsed.is_unspecified or parsed.is_loopback or parsed.is_multicast:
                    continue
                address = str(parsed)
                if address not in addresses:
                    addresses.append(address)
            except ipaddress.AddressValueError:
                continue
    return addresses[:4]


def store_tunnel_dns(interface: str, address: str, servers: list[str]) -> None:
    """Root-only metadata used when the guarded connection changes macOS DNS."""
    try:
        root = DNS_STATE.parent
        info = root.stat()
        if root.is_symlink() or info.st_uid != 0 or info.st_mode & 0o077:
            return
        temp = root / "tunnel-dns.next"
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"interface": interface, "address": address,
                       "servers": servers, "timestamp": int(time.time())}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, DNS_STATE)
    except OSError:
        pass



def validated_env(env: dict[str, str]) -> tuple[str, str, str, int]:
    reason = env.get("reason", "")
    if reason not in ("pre-init", "connect", "disconnect", "reconnect", "attempt-reconnect"):
        raise ValueError("CISCO_TUN_REASON_UNSUPPORTED")
    if reason in ("pre-init", "disconnect", "attempt-reconnect"):
        return reason, "", "", 0
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
    if reason in ("pre-init", "disconnect", "attempt-reconnect"):
        # Mac/OpenConnect owns the utun lifetime. Never delete a physical
        # address or network service, and don't modify routes or DNS.
        return "CISCO_UTUN_NO_SYSTEM_ROUTES"
    result = subprocess.run(
        [IFCONFIG, name, "inet", address, address,
         "netmask", "255.255.255.255", "mtu", str(mtu), "up"],
        capture_output=True, timeout=8, check=False)
    if result.returncode:
        raise ValueError("CISCO_UTUN_CONFIG_FAILED")
    store_tunnel_dns(name, address, tunnel_dns(env))
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
