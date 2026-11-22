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

from cisco_network_recovery import (snapshot as snapshot_network,
                                    restore as restore_network,
                                    record_tunnel_pid)
from cisco_openconnect_auth import validate, binary

SCRIPT = "/Library/PrivilegedHelperTools/TwinConnectCisco/vpnc-script"
ISOLATED_OPENCONNECT = "/Library/PrivilegedHelperTools/TwinConnectCisco/openconnect-runtime/bin/openconnect"
NETWORK_GUARD = "/Library/PrivilegedHelperTools/TwinConnectCisco/cisco_network_recovery.py"
CISCO_TUNNEL_ENABLED = False  # Must remain off until crash-safe route/IP/DNS restoration exists.
CISCO_UNPROTECTED_CONSOLE_TEST_ALLOWED = False  # Strict production safety interlock.

CISCO_RESULT_FILE = ("/private/var/run/twinconnect-cisco-route-guard/"
                     "last-result.json")


def record_cisco_result(reason: str) -> None:
    """Record a sanitized result for remote troubleshooting; no credentials."""
    if os.geteuid() != 0 or not re.fullmatch(r"CISCO_[A-Z0-9_]{3,60}", reason):
        return
    import stat
    import time
    root = os.path.dirname(CISCO_RESULT_FILE)
    try:
        info = os.stat(root)
        if info.st_uid != 0 or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
            return
        fd = os.open(CISCO_RESULT_FILE, os.O_CREAT | os.O_TRUNC |
                     os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"reason": reason, "timestamp": int(time.time())},
                      stream)
            stream.flush()
    except OSError:
        pass




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


def start_network_watchdog(console_trial: bool) -> None:
    if not trusted_root_owned_path(NETWORK_GUARD):
        raise ValueError("CISCO_NETWORK_GUARD_UNTRUSTED")
    watchdog = subprocess.Popen(
        ["/usr/bin/python3", NETWORK_GUARD, "watch", str(os.getpid()),
         "135" if console_trial else "600"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    if watchdog.poll() is not None:
        raise ValueError("CISCO_NETWORK_WATCHDOG_UNAVAILABLE")


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
    if not CISCO_TUNNEL_ENABLED:
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
    # The legacy console-test shortcut has no pinned management-client route.
    # It must never run on an externally managed VPS, even if another
    # safety switch is later enabled. Keep it only for mocked offline tests.
    if console_trial and not CISCO_UNPROTECTED_CONSOLE_TEST_ALLOWED:
        raise ValueError("CISCO_CONSOLE_MANAGEMENT_ROUTE_REQUIRED")
    local_desktop = management_ip == "desktop" or console_trial
    gateway = ""
    if not local_desktop:
        gateway, _ = management_route(management_ip)
    protected = False
    child = None
    checkpointed = False
    def requested_stop(_signum, _frame):
        raise KeyboardInterrupt

    previous_term = signal.signal(signal.SIGTERM, requested_stop)
    previous_int = signal.signal(signal.SIGINT, requested_stop)
    try:
        # Capture the original primary network service configuration before
        # either the management-route edit or vpnc-script can change it.
        snapshot_network()
        checkpointed = True
        # Independent watchdog outlives a crashed GUI or launcher.
        start_network_watchdog(console_trial)
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
        record_tunnel_pid(child.pid)
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
        try:
            if protected:
                subprocess.run([ROUTE, "-n", "delete", "-host", management_ip, gateway],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, check=False)
        finally:
            if checkpointed:
                # Keep the checkpoint if restore fails; detached watchdog
                # makes another attempt rather than silently losing recovery.
                restore_network()


CISCO_HOST_GUARD = ("/Library/PrivilegedHelperTools/TwinConnectCisco/"
                    "cisco_management_route_guard.py")


def cisco_tun_interfaces() -> dict[str, str]:
    """Observe only the configured private IPv4 on genuine utun devices."""
    listed = subprocess.run(["/sbin/ifconfig", "-l"], capture_output=True,
                            text=True, timeout=5, check=False)
    if listed.returncode:
        return {}
    found = {}
    for name in listed.stdout.split():
        if not re.fullmatch(r"utun[0-9]{1,4}", name):
            continue
        info = subprocess.run(["/sbin/ifconfig", name], capture_output=True,
                              text=True, timeout=5, check=False)
        if info.returncode:
            continue
        value = re.search(r"(?m)^\s*inet\s+([0-9.]+)\s+", info.stdout)
        if value:
            try:
                address = ipaddress.IPv4Address(value.group(1))
                if address.is_private and not address.is_loopback:
                    found[name] = str(address)
            except ipaddress.AddressValueError:
                continue
    return found


def cisco_verified_probe(baseline_interfaces: dict[str, str]) -> str:
    """One-destination HTTPS egress test; independent guard owns restoration."""
    if not trusted_root_owned_path(CISCO_HOST_GUARD):
        return "CISCO_EGRESS_GUARD_UNTRUSTED"
    available = cisco_tun_interfaces()
    created = [name for name in available
               if baseline_interfaces.get(name) != available[name]]
    if len(created) != 1:
        return "CISCO_EGRESS_TUN_NOT_IDENTIFIED"
    interface = created[0]
    guard = ["/usr/bin/python3", CISCO_HOST_GUARD]
    try:
        baseline = subprocess.run(
            ["/usr/bin/curl", "--noproxy", "*", "-4", "-fsS",
             "--connect-timeout", "3", "--max-time", "7",
             "https://1.1.1.1/cdn-cgi/trace"],
            capture_output=True, text=True, timeout=9, check=False)
        if baseline.returncode:
            return "CISCO_BASELINE_EGRESS_FAILED"
        original = re.search(r"(?m)^ip=([0-9.]+)$", baseline.stdout)
        if not original:
            return "CISCO_BASELINE_EGRESS_FAILED"
        trial = subprocess.run([*guard, "probe-host", interface],
                               capture_output=True, text=True, timeout=12,
                               check=False)
        if trial.returncode or trial.stdout.strip() != "CISCO_HOST_EGRESS_TRIAL_ACTIVE":
            return "CISCO_EGRESS_ROUTE_GUARD_REFUSED"
        try:
            tunnel = subprocess.run(
                ["/usr/bin/curl", "--noproxy", "*", "-4", "-fsS",
                 "--connect-timeout", "3", "--max-time", "8",
                 "https://1.1.1.1/cdn-cgi/trace"],
                capture_output=True, text=True, timeout=10, check=False)
            if tunnel.returncode:
                return "CISCO_EGRESS_HTTPS_FAILED"
            result = re.search(r"(?m)^ip=([0-9.]+)$", tunnel.stdout)
            if not result or result.group(1) == original.group(1):
                return "CISCO_EGRESS_NOT_VERIFIED"
            return "CISCO_EGRESS_VERIFIED"
        finally:
            restored = subprocess.run([*guard, "rollback"],
                                      capture_output=True, text=True,
                                      timeout=12, check=False)
            # A failed restore is unsafe even if the egress request succeeded.
            if restored.returncode or "ROLLBACK_VERIFIED" not in restored.stdout:
                raise ValueError("CISCO_EGRESS_ROLLBACK_INCOMPLETE")
    except (OSError, subprocess.TimeoutExpired):
        return "CISCO_EGRESS_TEST_UNAVAILABLE"


def probe_unrouted(profile: dict, system_vpn: bool = False) -> int:
    """Connect through isolated Cisco TUN, then verify data before full IPv4.

    The only privileged child network edit is the root-owned utun-only
    vpnc script. This does not certify full-device VPN, and the production
    Cisco gate remains closed. Keep the original uplink under observation
    to stop the candidate if any unexpected route change occurs.
    """
    if os.geteuid() != 0:
        raise ValueError("CISCO_ROOT_REQUIRED")
    script = "/Library/PrivilegedHelperTools/TwinConnectCisco/cisco_unrouted_vpnc.py"
    if not trusted_script(script):
        raise ValueError("CISCO_UNROUTED_SCRIPT_UNTRUSTED")
    if not os.path.isfile(ISOLATED_OPENCONNECT) or not os.access(
            ISOLATED_OPENCONNECT, os.X_OK):
        raise ValueError("CISCO_ISOLATED_OPENCONNECT_MISSING")
    if not trusted_openconnect_dependencies(ISOLATED_OPENCONNECT):
        raise ValueError("CISCO_UNTRUSTED_OPENCONNECT_DEPENDENCIES")
    if not profile.get("servercert"):
        raise ValueError("CISCO_PIN_REQUIRED_FOR_TUNNEL")
    baseline = subprocess.run(
        [ROUTE, "-n", "get", "default"], capture_output=True, text=True,
        timeout=5, check=False)
    if baseline.returncode:
        raise ValueError("CISCO_BASELINE_ROUTE_UNAVAILABLE")
    original = dict(ROUTE_GET.findall(baseline.stdout))
    if not original.get("gateway") or not re.fullmatch(
            r"en[0-9]{1,3}", original.get("interface", "")):
        raise ValueError("CISCO_BASELINE_ROUTE_UNSAFE")
    cmd = [
        ISOLATED_OPENCONNECT, "--protocol=anyconnect", "--no-proxy",
        "--non-inter", "--passwd-on-stdin", "--no-system-trust",
        "--user=" + profile["username"],
        "--servercert=" + profile["servercert"], "--script=" + script,
        "https://" + profile["host"] + ":" + str(profile["port"])
    ]
    initial_interfaces = cisco_tun_interfaces()
    child = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    # The UI's Stop Test sends SIGTERM to this privileged command.
    # Handle it in Python so the child process group is terminated first.
    def requested_stop(_signum, _frame):
        raise KeyboardInterrupt
    previous_term = signal.signal(signal.SIGTERM, requested_stop)
    previous_int = signal.signal(signal.SIGINT, requested_stop)
    try:
        assert child.stdin is not None
        child.stdin.write((profile["password"] + "\n").encode())
        child.stdin.close()
        print(json.dumps({"state": "cisco_unrouted_probe_started",
                          "vpn_connected": False}), flush=True)
        import time
        deadline = time.monotonic() + 90
        egress_reason = None
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise ValueError("CISCO_UNROUTED_ENGINE_EXITED")
            current = subprocess.run(
                [ROUTE, "-n", "get", "default"], capture_output=True,
                text=True, timeout=5, check=False)
            if current.returncode or dict(ROUTE_GET.findall(current.stdout)) != original:
                raise ValueError("CISCO_UNROUTED_ROUTE_CHANGED")
            # Wait for a new, actually configured Cisco utun before probing.
            if egress_reason is None and any(
                    initial_interfaces.get(k) != v
                    for k, v in cisco_tun_interfaces().items()):
                egress_reason = cisco_verified_probe(initial_interfaces)
                record_cisco_result(egress_reason)
                print(json.dumps({"state": "cisco_egress_probe",
                                  "reason": egress_reason,
                                  "vpn_connected": False}), flush=True)
            if egress_reason is not None:
                break
            time.sleep(1)
        if egress_reason is None:
            raise ValueError("CISCO_UNROUTED_TUNNEL_TIMEOUT")
        if egress_reason != "CISCO_EGRESS_VERIFIED":
            return 1
        if not system_vpn:
            return 0
        # Only after actual HTTPS egress is proven do we attempt guarded
        # /1 routes. The launchd watchdog restores routes and DNS on failure.
        created = [name for name, address in cisco_tun_interfaces().items()
                   if initial_interfaces.get(name) != address]
        if len(created) != 1:
            raise ValueError("CISCO_EGRESS_TUN_NOT_IDENTIFIED")
        guard = ["/usr/bin/python3", CISCO_HOST_GUARD]
        activated = subprocess.run([*guard, "activate-full", created[0],
                                    str(child.pid)], capture_output=True,
                                   text=True, timeout=29, check=False)
        if activated.returncode or activated.stdout.strip() != "CISCO_SYSTEM_IPV4_CONNECTED":
            raise ValueError("CISCO_SYSTEM_ROUTE_ACTIVATION_FAILED")
        record_cisco_result("CISCO_SYSTEM_IPV4_CONNECTED")
        print(json.dumps({"state": "connected",
                          "reason": "CISCO_SYSTEM_IPV4_CONNECTED",
                          "vpn_connected": True}), flush=True)
        # The privileged worker, not the GUI, renews the independent lease.
        # If its loop crashes, root launchd recovers routes within 45 seconds.
        while child.poll() is None:
            time.sleep(12)
            response = subprocess.run([*guard, "heartbeat", str(child.pid)],
                                      capture_output=True, text=True,
                                      timeout=12, check=False)
            if response.returncode or response.stdout.strip() != "CISCO_SYSTEM_IPV4_CONNECTED":
                raise ValueError("CISCO_SYSTEM_ROUTE_LEASE_LOST")
        raise ValueError("CISCO_ENGINE_EXITED")
    except KeyboardInterrupt:
        record_cisco_result("CISCO_SYSTEM_DISCONNECTED")
        print(json.dumps({"state": "cisco_unrouted_probe_stopped",
                          "vpn_connected": False}), flush=True)
        return 0
    finally:
        # Restore route and DNS before tearing down the interface, including
        # on SIGTERM, loss of engine or an exception inside the lease.
        if system_vpn:
            try:
                subprocess.run(["/usr/bin/python3", CISCO_HOST_GUARD,
                                "rollback"], capture_output=True,
                               text=True, timeout=12, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass  # independent watchdog still owns recovery
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(timeout=6)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=5)


def main() -> int:
    try:
        if sys.argv[1:] not in (["probe"], ["system"]) and (
                len(sys.argv) != 3 or sys.argv[1] != "connect"):
            raise ValueError("CISCO_INVALID_ACTION")
        # Validation before any privileged network operation.
        profile = validate(sys.stdin.buffer.read(16385))
        if not profile.get("servercert"):
            raise ValueError("CISCO_PIN_REQUIRED_FOR_TUNNEL")
        if sys.argv[1:] == ["probe"]:
            return probe_unrouted(profile)
        if sys.argv[1:] == ["system"]:
            return probe_unrouted(profile, system_vpn=True)
        return run(profile, sys.argv[2])
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        code = str(exc)
        if not re.fullmatch(r"CISCO_[A-Z0-9_]{3,60}", code):
            code = "CISCO_TUNNEL_FAILED"
        record_cisco_result(code)
        print(json.dumps({"state": "error", "reason": code,
                          "vpn_connected": False}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
