#!/usr/bin/env python3
"""Foreground, bounded local-console macOS TUN runner (no network installer).

Requires root-owned executable/config under /Library/PrivilegedHelperTools/TwinConnectTUN.
NEVER invoke on an SSH-connected or unattended remote Mac. Only a trusted
local administrator may choose to start it. No root elevation is performed.
The app's Connect button is intentionally NOT wired to this experimental runner.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import pwd
import signal
import subprocess
import sys
import time

from unsigned_tun_policy import TRUSTED_ROOT, preflight

MAX_RUNTIME_SECONDS = 3600


def verify_local_operator() -> None:
    """Necessary gate, not proof that remote management cannot be lost."""
    if platform.system() != "Darwin" or os.geteuid() != 0:
        raise ValueError("LOCAL_MACOS_ROOT_REQUIRED")
    if any(os.environ.get(k) for k in ("SSH_CONNECTION", "SSH_TTY", "SSH_CLIENT",
                                       "TWINCONNECT_REMOTE_VPS")):
        raise ValueError("REMOTE_SESSION_REFUSED")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise ValueError("INTERACTIVE_LOCAL_CONSOLE_REQUIRED")
    try:
        owner = os.stat("/dev/console").st_uid
        current = pwd.getpwnam(os.environ["SUDO_USER"]).pw_uid
    except (KeyError, OSError):
        raise ValueError("LOCAL_CONSOLE_OPERATOR_UNVERIFIED") from None
    if owner == 0 or owner != current:
        raise ValueError("LOCAL_CONSOLE_OPERATOR_UNVERIFIED")


def perform_run(binary: Path, config: Path, seconds: int) -> int:
    """Foreground engine with bounded lifetime and cleanup.

    Not a guarantee of network recovery after sudden power loss or a kernel
    panic. Production must use a supervised root-owned helper and recovery.
    """
    if not 1 <= seconds <= MAX_RUNTIME_SECONDS:
        raise ValueError("INVALID_MAX_RUNTIME")
    verify_local_operator()
    preflight(binary, config)
    subprocess.run([str(binary), "check", "-c", str(config)],
                   check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=20)
    child = subprocess.Popen([str(binary), "run", "-c", str(config)],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             start_new_session=True)
    deadline = time.monotonic() + seconds
    try:
        while child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        if child.poll() is not None:
            raise ValueError("TUN_ENGINE_EXITED")
        return 0
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "run"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--engine", type=Path, default=TRUSTED_ROOT / "sing-box")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--local-console-only", action="store_true")
    args = parser.parse_args()
    try:
        verify_local_operator()
        preflight(args.engine, args.config)
        if args.command == "preflight":
            print(json.dumps({"state": "preflight_passed",
                              "connected": False, "routes_changed": False}))
            return 0
        if not args.local_console_only:
            raise ValueError("EXPLICIT_LOCAL_CONSOLE_ACK_REQUIRED")
        print("LOCAL_TUN_STARTING; ROUTE_RESTORATION_NOT_GUARANTEED", flush=True)
        return perform_run(args.engine, args.config, args.seconds)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        reason = str(exc)
        if not (reason.isupper() and reason.replace("_", "").isalnum()
                and len(reason) <= 80):
            reason = "TUN_HELPER_FAILED"
        print(reason, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
