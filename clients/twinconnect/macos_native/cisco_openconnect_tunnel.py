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

SCRIPT = "/Library/PrivilegedHelperTools/TwinConnectCisco/vpnc-script"
ISOLATED_OPENCONNECT = "/Library/PrivilegedHelperTools/TwinConnectCisco/openconnect-runtime/bin/openconnect"


def trusted_script(path: str) -> bool:
    # Never let root launch the Homebrew copy owned by a normal user.
    try:
        st = os.lstat(path)
        parent = os.lstat(os.path.dirname(path))
    except OSError:
        return False
    import stat
    return (stat.S_ISREG(st.st_mode) and st.st_uid == 0 and
            not st.st_mode & 0o022 and
            stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0 and
            not parent.st_mode & 0o022 and
            bool(st.st_mode & 0o100))
def trusted_root_owned_path(path: str) -> bool:
    """Check real file and every parent against modification by non-root users."""
    import stat
    if not os.path.isabs(path):
        return False
    real = os.path.realpath(path)
    cursor = real
    try:
        while True:
            info = os.lstat(cursor)
            if info.st_uid != 0 or info.st_mode & 0o022:
                return False
            if cursor == real and not stat.S_ISREG(info.st_mode):
                return False
            if cursor != real and not stat.S_ISDIR(info.st_mode):
                return False
            parent = os.path.dirname(cursor)
            if cursor == parent:
                return True
            cursor = parent
    except OSError:
        return False


def trusted_openconnect_dependencies(executable: str) -> bool:
    """Refuse elevated Homebrew dylibs, including indirect dependencies.

    This is an admission check, not an installer or a claim that arbitrary
    plugins loaded at runtime are safe. Distribution requires a signed bundle.
    """
    pending = [executable]
    visited = set()
    while pending:
        current = pending.pop()
        current = os.path.realpath(current)
        if current in visited:
            continue
        visited.add(current)
        if len(visited) > 128 or not trusted_root_owned_path(current):
            return False
        try:
            output = subprocess.run(
                ["/usr/bin/otool", "-L", current], capture_output=True,
                text=True, timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if output.returncode:
            return False
        for line in output.stdout.splitlines()[1:]:
            dependency = line.strip().split(" (", 1)[0]
            if not dependency:
                continue
            if dependency.startswith(("/usr/lib/", "/System/Library/")):
                continue
            if dependency.startswith("@loader_path/"):
                resolved = os.path.realpath(os.path.join(
                    os.path.dirname(current), dependency[len("@loader_path/"):]))
                root = "/Library/PrivilegedHelperTools/TwinConnectCisco/openconnect-runtime/"
                if not resolved.startswith(root):
                    return False
                pending.append(resolved)
                continue
            if not dependency.startswith("/"):
                # Reject @rpath, @executable_path and unresolved references.
                return False
            if dependency.startswith(("/usr/local/", "/opt/homebrew/")):
                return False
            pending.append(dependency)
    return True


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
    # Safety interlock after the November 2026 macOS static IPv4 -> DHCP
    # incident. Do not permit privileged connections until network state
    # snapshot, verified restoration and crash recovery are implemented.
    raise ValueError("CISCO_TUNNEL_DISABLED_PENDING_NETWORK_RECOVERY")
    exe = ISOLATED_OPENCONNECT
    if not trusted_script(SCRIPT):
        raise ValueError("CISCO_TRUSTED_VPN_SCRIPT_REQUIRED")
    if not os.path.isfile(exe) or not os.access(exe, os.X_OK):
        raise ValueError("CISCO_ISOLATED_OPENCONNECT_MISSING")
    if not trusted_openconnect_dependencies(exe):
        raise ValueError("CISCO_UNTRUSTED_OPENCONNECT_DEPENDENCIES")
    script = SCRIPT
    # Console trial is explicitly provisioned by the administrator.
    # Automatically stop after two minutes, even if the app disappears.
    console_trial = management_ip == "console-test"
    local_desktop = management_ip == "desktop" or console_trial
    gateway = ""
    if not local_desktop:
        gateway, _ = management_route(management_ip)
    protected = False
    child = None
    def requested_stop(_signum, _frame):
        raise KeyboardInterrupt

    previous_term = signal.signal(signal.SIGTERM, requested_stop)
    previous_int = signal.signal(signal.SIGINT, requested_stop)
    try:
        if not local_desktop:
            route_add = subprocess.run(
                [ROUTE, "-n", "add", "-host", management_ip, gateway],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                check=False)
            if route_add.returncode:
                raise ValueError("CISCO_MANAGEMENT_ROUTE_PROTECTION_FAILED")
            protected = True
        cmd = [exe, "--protocol=anyconnect", "--no-proxy", "--non-inter",
               "--passwd-on-stdin", "--user=" + profile["username"],
               "--script=" + script, "--no-system-trust"]
        # Explicit certificate pin required for privileged route changes:
        # no trust-on-first-use or insecure certificate overrides.
        if not profile.get("servercert"):
            raise ValueError("CISCO_PIN_REQUIRED_FOR_TUNNEL")
        cmd.append("--servercert=" + profile["servercert"])
        cmd.append("https://" + profile["host"] + ":" + str(profile["port"]))
        child = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=False)
        assert child.stdin is not None
        child.stdin.write((profile["password"] + "\n").encode("utf-8"))
        child.stdin.close()
        print(json.dumps({"state": "cisco_tunnel_starting",
                          "vpn_connected": False}), flush=True)
        try:
            if console_trial:
                try:
                    return child.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    print(json.dumps({"state": "cisco_console_trial_timeout",
                                      "vpn_connected": False}), flush=True)
                    return 0
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
