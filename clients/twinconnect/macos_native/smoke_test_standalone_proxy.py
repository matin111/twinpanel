#!/usr/bin/env python3
"""One-shot macOS unsigned local proxy smoke test for an existing client profile.

Never changes default route/DNS, requires no sudo, and always requests engine
shutdown after the probe. Account config stays on this Mac; only status/IP
is printed. This is NOT a test of an entire system-wide VPN tunnel.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import sys
import time

from prepare_standalone_profile import prepare
from standalone_connection_manager import PROTOCOLS, SINGBOX, probe, read_state, process_matches, start, stop

CODES = ["v2ray", *sorted(SINGBOX)]


def smoke(protocol: str, source: Path, port: int, expected_ip: str | None,
          allow_same_exit: bool = False) -> dict:
    # Do not interfere with a preexisting manually managed VPN.
    old = read_state()
    if old and process_matches(old):
        raise ValueError("EXISTING_MANAGED_ENGINE_RUNNING_STOP_IT_MANUALLY_FIRST")
    if expected_ip is not None:
        try:
            expected_ip = str(ipaddress.IPv4Address(expected_ip))
        except ValueError:
            raise ValueError("EXPECTED_IP_MUST_BE_IPV4")
    generated = None
    launched = False
    result = None
    try:
        generated = Path(prepare(protocol, source, port)["path"])
        start(protocol, generated)
        launched = True
        # Remote tunnel handshake may be lazy; curl probe sends actual traffic.
        result = probe(expected_ip)
        if expected_ip is not None:
            passed = result["verified_expected_egress"]
        else:
            passed = result["state"] == "proxy_egress_reachable"
        result["test_passed"] = bool(passed)
        result["mode"] = "local_proxy_only"
        result["configuration_source_unchanged"] = True
        return result
    finally:
        if launched:
            stop()
        if generated is not None:
            generated.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", choices=CODES)
    parser.add_argument("client_config", type=Path)
    parser.add_argument("--port", type=int, default=10808)
    parser.add_argument("--expected-ip", default=None)
    args = parser.parse_args()
    try:
        result = smoke(args.protocol, args.client_config, args.port, args.expected_ip)
        print(json.dumps(result, indent=2))
        return 0 if result["test_passed"] else 2
    except (OSError, ValueError) as exc:
        # Never print config bodies, secrets, or process logs in errors.
        print(json.dumps({"state": "error", "reason": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
