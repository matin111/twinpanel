#!/usr/bin/env python3
"""Privileged Cisco AnyConnect TUN runtime for macOS.

Separate from the unsigned app's login diagnostic. Only explicit local root
invocation may alter routes/DNS. Never store or print authentication secrets.
A fixed management IPv4 route is installed before OpenConnect can replace
the default route; if route protection cannot be established, fail closed.
Do NOT run remotely unless a known management IPv4 is provided.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import signal
import subprocess
import sys

from cisco_openconnect_auth import validate, binary

SCRIPT = "/usr/local/etc/vpnc/vpnc-script"
ROUTE = "/sbin/route"
ROUTE_GET = re.compile(r"^\s*(gateway|interface):\s*(\S+)\s*$", re.M)


def management_route(ip: str) -> tuple[str, str]:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError("CISCO_MANAGEMENT_IP_INVALID")
    if address.version != 4 or not address.is_global:
        raise ValueError("CISCO_MANAGEMENT_IP_INVALID")
    found = subprocess.run([ROUTE, "-n", "get", ip], capture_output=True,
                           text=True, timeout=5, check=False)
    if found.returncode:
        raise ValueError("CISCO_MANAGEMENT_ROUTE_UNKNOWN")
    fields = dict(ROUTE_GET.findall(found.stdout))
    gateway = fields.get("gateway")
    interface = fields.get("interface")
    if (not interface or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,15}", interface)
            or not gateway):
        raise ValueError("CISCO_MANAGEMENT_ROUTE_UNKNOWN")
    try:
        gateway_ip = ipaddress.ip_address(gateway)
    except ValueError:
        raise ValueError("CISCO_MANAGEMENT_ROUTE_UNSAFE")
    if (gateway_ip.version != 4 or gateway_ip.is_loopback or
            gateway_ip.is_link_local or gateway_ip.is_multicast or
            gateway_ip.is_unspecified):
        raise ValueError("CISCO_MANAGEMENT_ROUTE_UNSAFE")
    return gateway, interface


def run(profile: dict, management_ip: str) -> int:
    if os.geteuid() != 0:
        raise ValueError("CISCO_ROOT_REQUIRED")
    exe = binary()
    if exe is None or not os.path.isfile(SCRIPT):
        raise ValueError("CISCO_ENGINE_UNAVAILABLE")
    gateway, _ = management_route(management_ip)
    protected = False
    child = None
    def requested_stop(_signum, _frame):
        raise KeyboardInterrupt

    previous_term = signal.signal(signal.SIGTERM, requested_stop)
    previous_int = signal.signal(signal.SIGINT, requested_stop)
    try:
        route_add = subprocess.run(
            [ROUTE, "-n", "add", "-host", management_ip, gateway],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
            check=False)
        if route_add.returncode:
            raise ValueError("CISCO_MANAGEMENT_ROUTE_PROTECTION_FAILED")
        protected = True
        cmd = [exe, "--protocol=anyconnect", "--no-proxy", "--non-inter",
               "--passwd-on-stdin", "--user=" + profile["username"],
               "--script=" + SCRIPT, "--no-system-trust"]
        # Explicit certificate pin required for privileged route changes:
        # no trust-on-first-use or insecure certificate overrides.
        if not profile.get("servercert"):
            raise ValueError("CISCO_PIN_REQUIRED_FOR_TUNNEL")
        cmd.append("--servercert=" + profile["servercert"])
        cmd.append("https://" + profile["host"] + ":" + str(profile["port"]))
        child = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        assert child.stdin is not None
        child.stdin.write((profile["password"] + "\n").encode("utf-8"))
        child.stdin.close()
        print(json.dumps({"state": "cisco_tunnel_starting",
                          "vpn_connected": False}), flush=True)
        try:
            return child.wait()
        except KeyboardInterrupt:
            return 0
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if protected:
            subprocess.run([ROUTE, "-n", "delete", "-host", management_ip, gateway],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, check=False)


def main() -> int:
    try:
        if len(sys.argv) != 3 or sys.argv[1] != "connect":
            raise ValueError("CISCO_INVALID_ACTION")
        management_ip = sys.argv[2]
        # Validation before any privileged route or tunnel change.
        profile = validate(sys.stdin.buffer.read(16385))
        if not profile.get("servercert"):
            raise ValueError("CISCO_PIN_REQUIRED_FOR_TUNNEL")
        return run(profile, management_ip)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        code = str(exc)
        if not re.fullmatch(r"CISCO_[A-Z0-9_]{3,60}", code):
            code = "CISCO_TUNNEL_FAILED"
        print(json.dumps({"state": "error", "reason": code,
                          "vpn_connected": False}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
