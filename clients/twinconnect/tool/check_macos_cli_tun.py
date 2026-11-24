#!/usr/bin/env python3
"""Read-only readiness check for the no-Apple-Developer macOS CLI TUN route.

A command-line sing-box TUN helper may avoid Network Extension signing,
but requires appropriate local privileges and careful route/restore handling.
THIS TOOL NEVER STARTS AN ENGINE, READS VPN SECRETS, OR CHANGES NETWORKING.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform


ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURES = {"x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}


def probe(root: Path = ROOT, *, system: str | None = None,
          machine: str | None = None) -> dict:
    system = system if system is not None else platform.system()
    machine = machine if machine is not None else platform.machine()
    arch = ARCHITECTURES.get(machine)
    # Only the repository's dedicated CLI binary location is considered.
    # The PacketTunnel.appex's linked Libbox isn't a standalone sing-box.
    binary = (root / "macos_native/build/singbox" / arch / "sing-box"
              if arch else None)
    executable = bool(binary and binary.is_file() and
                      os.access(binary, os.X_OK))
    remote = bool(os.environ.get("SSH_CONNECTION") or
                  os.environ.get("SSH_TTY"))
    checks = {
        "macos": system == "Darwin",
        "supported_architecture": arch is not None,
        "singbox_cli_executable_present": executable,
    }
    return {
        "mode": "read_only_cli_tun_preflight",
        "result": ("ENGINE_BINARY_PRESENT_NOT_TUN_VERIFIED"
                   if all(checks.values()) else
                   "CLI_TUN_NOT_READY"),
        "checks": checks,
        "candidate_binary": str(binary) if executable else None,
        "requires_apple_developer_packet_tunnel_entitlement": False,
        "administrator_privileges_required_for_system_tun": True,
        "interactive_administrator_approval_performed": False,
        "remote_shell_detected": remote,
        "remote_access_loss_risk": True,
        "connection_started": False,
        "default_route_modified": False,
        "dns_modified": False,
        "system_proxy_modified": False,
        "next": ("Verify sing-box version and TUN routing in a separately "
                 "recoverable test environment before enabling any route"
                 if executable else
                 "Build or install a compatible standalone sing-box CLI "
                 "binary for this Mac before attempting TUN"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(probe(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
