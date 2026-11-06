#!/usr/bin/env python3
"""Opt-in per-V2Ray-port VXLAN overlay for the known TwinPanel Iran ingress.

Never modifies managed TP_DNAT, TP_SNAT, TP_FWD, tunnels, Xray, or any
non-V2Ray protocol. This deliberately does NOT auto-activate on install.
"""
from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess

# Reviewed topology only: Iran 9 -> Exits Germany 7 and USA 11.
# Other VPN protocols continue using their existing desired-state route.
ROUTES = {
    "de-ws": dict(port=26007, target_port=9444,
                  device="tpvx30", local="10.243.0.121",
                  peer="10.243.0.122"),
    "us-ws": dict(port=26011, target_port=9444,
                  device="tpvx32", local="10.243.0.129",
                  peer="10.243.0.130"),
    "de-xhttp": dict(port=24007, target_port=9447,
                  device="tpvx30", local="10.243.0.121",
                  peer="10.243.0.122"),
    "de-tcp": dict(port=28007, target_port=9446,
                  device="tpvx30", local="10.243.0.121",
                  peer="10.243.0.122"),
    "us-xhttp": dict(port=24011, target_port=9447,
                  device="tpvx32", local="10.243.0.129",
                  peer="10.243.0.130"),
    "us-tcp": dict(port=28011, target_port=9446,
                  device="tpvx32", local="10.243.0.129",
                  peer="10.243.0.130"),
}


def invoke(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(args), capture_output=True, text=True,
        check=check, timeout=12,
    )


def rules(route: dict) -> tuple[list[str], list[str]]:
    port = str(int(route["port"]))
    target_port = str(int(route["target_port"]))
    interface = str(route["device"])
    destination = str(ipaddress.IPv4Address(route["peer"]))
    source = str(ipaddress.IPv4Address(route["local"]))
    dnat = [
        "-i", "eth0", "-p", "tcp", "--dport", port,
        "-j", "DNAT", "--to-destination", destination + ":" + target_port,
    ]
    snat = [
        "-o", interface, "-d", destination, "-p", "tcp",
        "--dport", target_port, "-m", "conntrack",
        "--ctorigdstport", port,
        "-j", "SNAT", "--to-source", source,
    ]
    return dnat, snat


def contains(chain: str, rule: list[str]) -> bool:
    result = invoke("iptables", "-w", "5", "-t", "nat", "-C", chain, *rule, check=False)
    return result.returncode == 0


def update(chain: str, operation: str, rule: list[str]) -> None:
    invoke("iptables", "-w", "5", "-t", "nat", operation, chain, *rule)


def validate_topology(route: dict) -> None:
    dev = route["device"]
    ip = route["local"]
    result = invoke("ip", "-4", "-o", "address", "show", "dev", dev)
    if not re.search(r"(?<![\d.])" + re.escape(ip) + r"/\d+", result.stdout):
        raise RuntimeError("VXLAN source address mismatches audited ingress")
    route_get = invoke("ip", "-4", "route", "get", route["peer"])
    if "dev " + dev not in route_get.stdout:
        raise RuntimeError("VXLAN destination is not routed through expected interface")
    agent = invoke("systemctl", "is-active", "twinpanel-agent", check=False)
    if agent.returncode != 0:
        raise RuntimeError("Iran node agent is inactive, refusing route change")


def ensure_port_exclusive(route: dict, dnat: list[str]) -> None:
    current = invoke("iptables", "-w", "5", "-t", "nat", "-S", "PREROUTING").stdout
    port_token = "--dport " + str(route["port"])
    matching = [line for line in current.splitlines() if port_token in line]
    if any(("--to-destination " + route["peer"] + ":" + str(route["target_port"])) not in line
           for line in matching):
        raise RuntimeError("Conflicting PREROUTING override exists for V2Ray canary")


def ensure_priority(dnat: list[str]) -> None:
    listed = invoke("iptables", "-w", "5", "-t", "nat", "-S", "PREROUTING").stdout
    active = [line for line in listed.splitlines() if line.startswith("-A PREROUTING ")]
    if not active:
        raise RuntimeError("PREROUTING unexpectedly empty")
    expected_port = "--dport " + str(dnat[dnat.index("--dport") + 1])
    positions = [i for i, line in enumerate(active) if expected_port in line]
    managed = [i for i, line in enumerate(active) if "-j TP_DNAT" in line]
    if len(positions) != 1 or not managed:
        raise RuntimeError("V2Ray canary NAT placement ambiguous")
    if positions[0] >= min(managed):
        # Only restore priority over Agent jumps; never churn the relative
        # order of two healthy V2Ray-only canary routes every minute.
        update("PREROUTING", "-D", dnat)
        update("PREROUTING", "-I", ["1", *dnat])


def apply(route: dict) -> None:
    validate_topology(route)
    dnat, snat = rules(route)
    ensure_port_exclusive(route, dnat)
    inserted_snat = False
    try:
        if not contains("POSTROUTING", snat):
            update("POSTROUTING", "-I", ["1", *snat])
            inserted_snat = True
        if not contains("PREROUTING", dnat):
            update("PREROUTING", "-I", ["1", *dnat])
        else:
            ensure_priority(dnat)
        if not contains("PREROUTING", dnat) or not contains("POSTROUTING", snat):
            raise RuntimeError("V2Ray-only route verification failed")
    except Exception:
        if inserted_snat and contains("POSTROUTING", snat):
            update("POSTROUTING", "-D", snat)
        raise
    print("V2RAY_VXLAN_CANARY=active", route["port"], route["device"])


def remove(route: dict) -> None:
    dnat, snat = rules(route)
    if contains("PREROUTING", dnat):
        update("PREROUTING", "-D", dnat)
    if contains("POSTROUTING", snat):
        update("POSTROUTING", "-D", snat)
    print("V2RAY_VXLAN_CANARY=removed", route["port"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["apply", "remove", "status"])
    parser.add_argument("--profile", choices=sorted(ROUTES), default="de-ws")
    a = parser.parse_args()
    route = ROUTES[a.profile]
    if a.action == "apply":
        apply(route)
    elif a.action == "remove":
        remove(route)
    else:
        dnat, snat = rules(route)
        print("V2RAY_VXLAN_CANARY", a.profile,
              "dnat", contains("PREROUTING", dnat),
              "snat", contains("POSTROUTING", snat))


if __name__ == "__main__":
    main()
