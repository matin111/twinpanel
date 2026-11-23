#!/usr/bin/env python3
"""Bounded macOS root smoke test of unsigned wireguard-go's utun creation.

Does NOT load VPN credentials, change IP/route/DNS, configure peers or establish
VPN egress. Launches a fresh unconfigured utun for <=5 seconds and removes it.
Never test over a live Cisco or OpenVPN full-route session.
"""
from __future__ import annotations
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parents[1]
GUARD = Path("/Library/PrivilegedHelperTools/TwinConnectCisco/"
             "cisco_management_route_guard.py")


def run(*cmd: str) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL,
                                   timeout=6).strip()


def route() -> tuple[str, str]:
    output = run("/sbin/route", "-n", "get", "default")
    from re import search
    gateway = search(r"(?m)^\s*gateway:\s*(\S+)", output)
    interface = search(r"(?m)^\s*interface:\s*(\S+)", output)
    if not gateway or not interface:
        raise RuntimeError("WG_BASELINE_ROUTE_UNAVAILABLE")
    return gateway.group(1), interface.group(1)


def interfaces() -> set[str]:
    return set(run("/sbin/ifconfig", "-l").split())


def main() -> int:
    if sys.platform != "darwin" or os.geteuid() != 0:
        print("WG_MACOS_ROOT_REQUIRED")
        return 2
    original = route()
    if original[1] != "en0":
        print("WG_PROBE_REFUSES_NON_PHYSICAL_DEFAULT")
        return 2
    if GUARD.is_file() and run("/usr/bin/python3", str(GUARD), "status") != \
            "CISCO_MANAGEMENT_PIN_IDLE":
        print("WG_PROBE_REFUSES_ACTIVE_CISCO")
        return 2
    binary = HERE / "macos_native/build/wireguard-userspace" / (
        "amd64" if os.uname().machine == "x86_64" else "arm64"
    ) / "wireguard-go"
    if not binary.is_file() or binary.is_symlink() or not os.access(binary, os.X_OK):
        print("WG_UNSIGNED_ENGINE_NOT_BUILT")
        return 2
    previous = interfaces()
    target = next((f"utun{i}" for i in range(15, 40)
                   if f"utun{i}" not in previous), None)
    if target is None:
        print("WG_SAFE_UTUN_NAME_UNAVAILABLE")
        return 2
    process = subprocess.Popen(
        [str(binary), "-f", target],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    made = False
    try:
        for _ in range(20):
            time.sleep(0.25)
            if process.poll() is not None:
                break
            if target in interfaces():
                made = True
                break
        if not made or process.poll() is not None:
            print("WG_UNSIGNED_UTUN_CREATION_FAILED")
            return 1
        if route() != original:
            print("WG_UNEXPECTED_DEFAULT_ROUTE_CHANGE")
            return 1
        print("WG_UNSIGNED_UTUN_CREATED_WITHOUT_SYSTEM_ROUTE")
        return 0
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=4)
        if route() != original or target in interfaces():
            print("WG_UNSIGNED_PROBE_CLEANUP_UNVERIFIED")
        else:
            print("WG_UNSIGNED_PROBE_CLEANUP_VERIFIED")


if __name__ == "__main__":
    raise SystemExit(main())
