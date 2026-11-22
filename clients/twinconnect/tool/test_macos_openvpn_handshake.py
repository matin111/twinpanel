#!/usr/bin/env python3
"""Bounded real OpenVPN handshake test on a macOS host.

Run only by an administrator who has recovery access:
  sudo /usr/bin/python3 tool/test_macos_openvpn_handshake.py ~/Downloads/client.ovpn

This test creates a temporary utun interface, but deliberately prevents
default-route/DNS imports and does not claim system-wide VPN egress.
It always attempts to stop the OpenVPN process group and delete credentials.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time

# The repo's reviewer is deliberately NOT imported via writable PYTHONPATH.
HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / "macos_native"))
from openvpn_profile_review import review, MAX_PROFILE_BYTES

MAX_SECONDS = 35
ROOTS = (
    Path("/usr/local/opt/openvpn/sbin/openvpn"),
    Path("/opt/homebrew/opt/openvpn/sbin/openvpn"),
)
SUCCESS = "Initialization Sequence Completed"
STATUS_MARKERS = (
    ("AUTH_FAILED", "OPENVPN_AUTH_FAILED"),
    ("VERIFY ERROR", "OPENVPN_CERT_VERIFY_FAILED"),
    ("TLS Error", "OPENVPN_TLS_FAILED"),
    ("Options error", "OPENVPN_OPTIONS_ERROR"),
    ("Cannot open TUN", "OPENVPN_UTUN_UNAVAILABLE"),
    ("Exiting due to fatal error", "OPENVPN_FATAL_ERROR"),
)


def current_default_route() -> tuple[str, str] | None:
    try:
        result = subprocess.run(
            ["/sbin/route", "-n", "get", "default"],
            check=False, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    found = {}
    for row in result.stdout.splitlines():
        name, separator, value = row.strip().partition(":")
        if separator and name in ("gateway", "interface"):
            found[name] = value.strip()
    if not found.get("gateway") or not found.get("interface"):
        return None
    return found["gateway"], found["interface"]


def sanitize_profile(raw: bytes) -> bytes:
    if not raw or len(raw) > MAX_PROFILE_BYTES:
        raise ValueError("OPENVPN_PROFILE_SIZE_INVALID")
    checked = review(raw.decode("utf-8", errors="strict"))
    if "remote-cert-tls server" not in checked["directives"]:
        raise ValueError("OPENVPN_CERTIFICATE_ROLE_REQUIRED")
    # Reconstruct instead of passing unreviewed server directives to root.
    lines = list(checked["directives"])
    for tag, payload in checked["inline"].items():
        lines.extend(["<" + tag + ">", payload.rstrip("\n"), "</" + tag + ">"])
    return ("\n".join(lines) + "\n").encode("utf-8")


def stop_group(child: subprocess.Popen) -> None:
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=5)


def report(log: bytes, exit_code: int | None) -> str:
    # Never print raw OpenVPN logs, certificate identities or passwords.
    output = log.decode("utf-8", errors="replace")
    if SUCCESS in output:
        return "OPENVPN_HANDSHAKE_VERIFIED"
    for marker, code in STATUS_MARKERS:
        if marker in output:
            return code
    return "OPENVPN_NO_HANDSHAKE" if exit_code is None else "OPENVPN_EXITED_BEFORE_HANDSHAKE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    if platform.system() != "Darwin" or os.geteuid() != 0:
        print("MACOS_ROOT_REQUIRED")
        return 2
    if args.profile.is_symlink() or not args.profile.is_file():
        print("OPENVPN_PROFILE_MISSING")
        return 2
    engine = next((p for p in ROOTS if p.is_file() and os.access(p, os.X_OK)), None)
    if engine is None:
        print("OPENVPN_ENGINE_MISSING")
        return 2
    try:
        prepared = sanitize_profile(args.profile.read_bytes())
    except (ValueError, OSError, UnicodeError):
        print("OPENVPN_PROFILE_REJECTED")
        return 2
    before = current_default_route()
    if before is None:
        print("OPENVPN_DEFAULT_ROUTE_NOT_OBSERVABLE")
        return 2
    child = None
    handshake = False
    changed = False
    exit_code = None
    logs = b""
    # Config and logs are never written to the repository or sent to the panel.
    with tempfile.TemporaryDirectory(prefix="twinconnect-ovpn-test-") as folder:
        os.chmod(folder, 0o700)
        config = Path(folder) / "client.ovpn"
        fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(prepared)
        log_path = Path(folder) / "engine.log"
        with open(log_path, "ab", buffering=0) as output:
            command = [str(engine), "--config", str(config),
                       "--route-nopull", "--script-security", "1",
                       "--auth-nocache", "--verb", "3"]
            try:
                child = subprocess.Popen(
                    command, stdin=subprocess.DEVNULL,
                    stdout=output, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                deadline = time.monotonic() + MAX_SECONDS
                while time.monotonic() < deadline:
                    if current_default_route() != before:
                        changed = True
                        break
                    # Read via a separate descriptor; never seek on the
                    # descriptor inherited by OpenVPN as stdout/stderr.
                    with open(log_path, "rb") as reader:
                        logs = reader.read(1024 * 1024)
                    if SUCCESS.encode() in logs:
                        handshake = True
                        break
                    if child.poll() is not None:
                        break
                    time.sleep(0.5)
            except OSError:
                print("OPENVPN_START_FAILED")
                return 3
            finally:
                if child is not None:
                    exit_code = child.poll()
                    stop_group(child)
                with open(log_path, "rb") as reader:
                    logs = reader.read(1024 * 1024)
    after = current_default_route()
    if changed or before != after:
        print("OPENVPN_DEFAULT_ROUTE_CHANGED_STOPPED")
        return 4
    print("DEFAULT_ROUTE_UNCHANGED")
    print("OPENVPN_TEST_STOPPED")
    print("OPENVPN_HANDSHAKE_VERIFIED" if handshake else report(logs, exit_code))
    print("SYSTEM_VPN_EGRESS_NOT_TESTED")
    return 0 if handshake else 1


if __name__ == "__main__":
    raise SystemExit(main())
