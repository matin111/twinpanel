#!/usr/bin/env python3
"""Local-only macOS VPN evidence capture; deliberately not a handshake oracle.

Usage:
  python3 macos_native/capture_hysteria2_network_evidence.py sample \
    --phase baseline --output /tmp/twin-before.json --probe-egress
  # Start Hysteria2 from a *signed* TwinConnect app, then:
  python3 macos_native/capture_hysteria2_network_evidence.py sample \
    --phase connected --output /tmp/twin-after.json --probe-egress
  python3 macos_native/capture_hysteria2_network_evidence.py compare \
    --before /tmp/twin-before.json --after /tmp/twin-after.json

Do not upload these local files: network addresses are sensitive.
--probe-egress explicitly opts into an HTTPS query to api.ipify.org.
DNS leak checks and a Hysteria2 peer handshake require additional live tests.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit("MAC_NETWORK_EVIDENCE_ERROR: " + message)


def command(*args: str) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=15,
                          check=False)
    if proc.returncode:
        fail("cannot read macOS network state: " + args[0])
    return proc.stdout


def extract_interface(route: str) -> str | None:
    match = re.search(r"(?m)^\s*interface:\s*(\S+)", route)
    return match.group(1) if match else None


def public_ipv4() -> str:
    req = urllib.request.Request(
        "https://api.ipify.org", headers={"User-Agent": "TwinConnect-Mac-Manual-Test/1"}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            data = response.read(48).decode("ascii", "strict").strip()
        address = ipaddress.ip_address(data)
        if address.version != 4 or not address.is_global:
            fail("egress service did not return a public IPv4 address")
        return str(address)
    except (OSError, ValueError, UnicodeError) as exc:
        fail("opt-in IPv4 egress request failed: " + type(exc).__name__)


def sample(phase: str, output: Path, probe_egress: bool) -> None:
    if sys.platform != "darwin":
        fail("network evidence sampling requires a real macOS host")
    if output.exists():
        fail("refusing to overwrite previous evidence: " + str(output))
    route = command("route", "-n", "get", "default")
    dns = command("scutil", "--dns")
    interfaces = command("ifconfig", "-l").strip().split()
    evidence = {
        "schema": 1,
        "phase": phase,
        "default_route_interface": extract_interface(route),
        "network_interfaces": sorted(interfaces),
        "dns_config_sha256": hashlib.sha256(dns.encode()).hexdigest(),
        "egress_ipv4": public_ipv4() if probe_egress else None,
        "probe_egress_opted_in": probe_egress,
        "vpn_peer_handshake_verified": False,
        "dns_leak_verified": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    handle = os.open(output, flags, 0o600)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(evidence, stream, indent=2)
            stream.write("\n")
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    print("EVIDENCE_CAPTURED_LOCALLY")
    print("PHASE=" + phase)
    print("FILE_MODE=0600")
    print("HANDSHAKE_AND_DNS_LEAKS=NOT_VERIFIED")


def compare(before: dict, after: dict) -> bool:
    if before.get("schema") != 1 or after.get("schema") != 1:
        fail("evidence schemas do not match")
    if before.get("phase") != "baseline" or after.get("phase") != "connected":
        fail("expected baseline and connected phase evidence")
    for sample in (before, after):
        if sample.get("vpn_peer_handshake_verified") is not False:
            fail("unsupported handshake verification claim in evidence")
        if sample.get("dns_leak_verified") is not False:
            fail("unsupported DNS leak verification claim in evidence")
    first = before.get("egress_ipv4")
    last = after.get("egress_ipv4")
    changed = (isinstance(first, str) and isinstance(last, str)
               and first != last)
    if changed:
        # Changed IP does not independently prove which protocol carried it.
        print("EXTERNAL_IPV4_CHANGED=YES")
    else:
        print("EXTERNAL_IPV4_CHANGED=NO_OR_NOT_MEASURED")
    was = set(before.get("network_interfaces") or [])
    now = set(after.get("network_interfaces") or [])
    appeared = sorted(x for x in now - was if x.startswith("utun"))
    print("NEW_UTUN_INTERFACE_PRESENT=" + ("YES" if appeared else "NO"))
    print("ROUTE_INTERFACE_CHANGED=" + (
        "YES" if before.get("default_route_interface") !=
        after.get("default_route_interface") else "NO"))
    print("DNS_CONFIGURATION_CHANGED=" + (
        "YES" if before.get("dns_config_sha256") !=
        after.get("dns_config_sha256") else "NO"))
    print("HYSTERIA2_HANDSHAKE_VERIFIED=NO")
    print("DNS_LEAK_VERIFIED=NO")
    print("CONNECTION_PROVEN=NO")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    collect = sub.add_parser("sample")
    collect.add_argument("--phase", choices=("baseline", "connected"), required=True)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--probe-egress", action="store_true")
    check = sub.add_parser("compare")
    check.add_argument("--before", type=Path, required=True)
    check.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "sample":
        sample(args.phase, args.output, args.probe_egress)
    else:
        try:
            with args.before.open(encoding="utf-8") as stream:
                before = json.load(stream)
            with args.after.open(encoding="utf-8") as stream:
                after = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            fail("invalid evidence file: " + type(exc).__name__)
        if not compare(before, after):
            fail("insufficient evidence of an external IPv4 change")


if __name__ == "__main__":
    main()
