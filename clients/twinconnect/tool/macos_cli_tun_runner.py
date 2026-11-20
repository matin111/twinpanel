#!/usr/bin/env python3
"""Fail-closed, bounded sing-box TUN runner for macOS.

This is a developer diagnostic, NOT a system-wide VPN or app integration.
It explicitly forbids automatic routing to protect remote/cloud Macs.
It never prompts for sudo, modifies system routes/DNS, or persists secrets.
Use only in a recoverable environment with a separately prepared config.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARCH = {"x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}
MAX_SECONDS = 120


def validate_config(config: Path) -> dict:
    if not config.is_file() or config.is_symlink():
        raise ValueError("Regular config file required")
    if config.stat().st_size > 2_000_000:
        raise ValueError("Config file too large")
    data = json.loads(config.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Config root must be object")
    inbounds = data.get("inbounds", [])
    if not isinstance(inbounds, list) or not inbounds:
        raise ValueError("At least one inbound required")
    tuns = [i for i in inbounds if isinstance(i, dict) and i.get("type") == "tun"]
    if len(tuns) != 1:
        raise ValueError("Exactly one TUN inbound required")
    tun = tuns[0]
    if tun.get("auto_route") is not False:
        raise ValueError("auto_route must be explicitly false")
    if tun.get("auto_redirect", False) is not False:
        raise ValueError("auto_redirect must be false")
    if tun.get("strict_route", False) is not False:
        raise ValueError("strict_route must be false")
    if data.get("experimental", {}).get("cache_file", {}).get("enabled"):
        raise ValueError("Persistent cache disabled for diagnostic")
    # Avoid system-wide changes through platform-specific settings.
    if "platform" in tun or "route_address_set" in tun or "route_exclude_address_set" in tun:
        raise ValueError("Platform route modifiers not allowed")
    return data


def engine_path() -> Path:
    arch = ARCH.get(platform.machine())
    if platform.system() != "Darwin" or not arch:
        raise RuntimeError("Only supported on macOS x86_64/arm64")
    binary = ROOT / "macos_native/build/singbox" / arch / "sing-box"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("Standalone sing-box executable missing")
    return binary


def run_diagnostic(binary: Path, config: Path, seconds: int) -> int:
    if os.geteuid() != 0:
        raise RuntimeError("TUN requires explicit administrator/root invocation; no automatic elevation")
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        raise RuntimeError("Refusing TUN from SSH session; use recoverable local console")
    # sing-box check validates configuration without modifying networking.
    subprocess.run([str(binary), "check", "-c", str(config)], check=True, timeout=20)
    proc = subprocess.Popen([str(binary), "run", "-c", str(config)],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True)
    deadline = time.monotonic() + seconds
    try:
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        return proc.returncode if proc.returncode is not None else 0
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run-local-diagnostic", action="store_true")
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()
    try:
        if not 1 <= args.seconds <= MAX_SECONDS:
            raise ValueError("seconds must be between 1 and 120")
        config = args.config.expanduser().resolve(strict=True)
        validate_config(config)
        binary = engine_path()
        subprocess.run([str(binary), "check", "-c", str(config)], check=True, timeout=20)
        if not args.run_local_diagnostic:
            print("CONFIG_VALIDATED_ONLY: no connection started; routes and DNS unchanged by this tool")
            return 0
        print("Starting bounded local diagnostic; not system-wide routed VPN", flush=True)
        return run_diagnostic(binary, config, args.seconds)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"CLI_TUN_BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
