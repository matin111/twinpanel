#!/usr/bin/env python3
"""Fail-closed macOS network checkpoint and recovery for Cisco/OpenConnect.

Captures the *current* primary network service and IPv4/DNS settings, never
bakes a particular VPS address into a distributed application. Must be run
as root. Restores only a previously validated, root-owned checkpoint.
No network change is made by inspect/snapshot.
"""
from __future__ import annotations
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASE = Path("/Library/PrivilegedHelperTools/TwinConnectCisco")
CHECKPOINT = BASE / "network-checkpoint.json"
NETWORKSETUP = "/usr/sbin/networksetup"
ROUTE = "/sbin/route"
MAX_READ = 16384


def command(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        raise ValueError("CISCO_NETWORK_COMMAND_FAILED")
    return result.stdout[:MAX_READ]


def valid_ipv4(ip: str) -> str:
    try:
        addr = ipaddress.IPv4Address(ip)
    except ipaddress.AddressValueError:
        raise ValueError("CISCO_NETWORK_INVALID_IPV4")
    if (addr.is_loopback or addr.is_link_local or addr.is_multicast
            or addr.is_unspecified):
        raise ValueError("CISCO_NETWORK_INVALID_IPV4")
    return str(addr)


def default_interface() -> str:
    data = command(ROUTE, "-n", "get", "default")
    match = re.search(r"^\s*interface:\s*([a-zA-Z][a-zA-Z0-9]{0,15})\s*$",
                      data, re.M)
    if not match:
        raise ValueError("CISCO_NETWORK_NO_DEFAULT_INTERFACE")
    return match.group(1)


def network_service_for_device(device: str) -> str:
    # The first line of a two-line entry contains the network service name;
    # the next reports the actual device bound to that service.
    data = command(NETWORKSETUP, "-listnetworkserviceorder")
    pattern = r"(?m)^\(\d+\) (.+)\n\(Hardware Port: [^\n]+, Device: " + re.escape(device) + r"\)"
    found = re.search(pattern, data)
    if not found or not found.group(1) or found.group(1).startswith("*"):
        raise ValueError("CISCO_NETWORK_SERVICE_NOT_FOUND")
    return found.group(1)


def capture() -> dict:
    if os.geteuid() != 0:
        raise ValueError("CISCO_ROOT_REQUIRED")
    device = default_interface()
    service = network_service_for_device(device)
    details = command(NETWORKSETUP, "-getinfo", service)
    if "Manual Configuration" in details:
        mode = "manual"
    elif "DHCP Configuration" in details:
        mode = "dhcp"
    else:
        raise ValueError("CISCO_NETWORK_UNKNOWN_IPV4_MODE")
    fields = dict(re.findall(r"(?m)^([^:\n]+):\s*([^\n]+)$", details))
    ip = valid_ipv4(fields.get("IP address", ""))
    if mode == "manual":
        mask = valid_ipv4(fields.get("Subnet mask", ""))
        gateway = valid_ipv4(fields.get("Router", ""))
        try:
            ipaddress.IPv4Network("0.0.0.0/" + mask)
        except ValueError:
            raise ValueError("CISCO_NETWORK_INVALID_MASK")
    else:
        mask, gateway = "", ""
    dns_raw = command(NETWORKSETUP, "-getdnsservers", service).strip()
    dns = []
    if not dns_raw.lower().startswith("there aren't any dns servers"):
        for line in dns_raw.splitlines():
            value = line.strip()
            if value:
                dns.append(valid_ipv4(value))
    if len(dns) > 8:
        raise ValueError("CISCO_NETWORK_TOO_MANY_DNS")
    if mode == "manual":
        # A static IPv4 address must still have a valid default route.
        current_default = default_interface()
        if current_default != device:
            raise ValueError("CISCO_NETWORK_DEFAULT_ROUTE_MISMATCH")
    return {"version": 1, "interface": device, "service": service,
            "mode": mode, "ip": ip, "mask": mask, "gateway": gateway,
            "dns": dns}


def snapshot() -> dict:
    data = capture()
    if CHECKPOINT.exists():
        raise ValueError("CISCO_NETWORK_CHECKPOINT_EXISTS")
    fd = os.open(str(CHECKPOINT), os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(data, file)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        CHECKPOINT.unlink(missing_ok=True)
        raise
    return data


def read_checkpoint() -> dict:
    import stat
    info = os.lstat(CHECKPOINT)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError("CISCO_NETWORK_CHECKPOINT_UNTRUSTED")
    with CHECKPOINT.open() as file:
        value = json.load(file)
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("CISCO_NETWORK_CHECKPOINT_INVALID")
    if value.get("mode") not in {"manual", "dhcp"}:
        raise ValueError("CISCO_NETWORK_CHECKPOINT_INVALID")
    if not isinstance(value.get("dns"), list):
        raise ValueError("CISCO_NETWORK_CHECKPOINT_INVALID")
    for name in ("ip", "mask", "gateway"):
        if value.get(name):
            valid_ipv4(value[name])
    for item in value["dns"]:
        valid_ipv4(item)
    if not isinstance(value.get("service"), str) or not value["service"]:
        raise ValueError("CISCO_NETWORK_CHECKPOINT_INVALID")
    return value


def record_tunnel_pid(pid: int) -> None:
    """Atomically attach the privileged child PID to the root-only checkpoint."""
    if os.geteuid() != 0 or type(pid) is not int or pid <= 1:
        raise ValueError("CISCO_NETWORK_PID_INVALID")
    state = read_checkpoint()
    state["tunnel_pid"] = pid
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix=".cisco-state-", dir=BASE)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, CHECKPOINT)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def stop_orphaned_tunnel() -> None:
    """Only signal the exact installed OpenConnect binary if still running."""
    import signal
    state = read_checkpoint()
    pid = state.get("tunnel_pid")
    if type(pid) is not int or pid <= 1:
        return
    p = subprocess.run(
        ["/bin/ps", "-p", str(pid), "-o", "command="],
        capture_output=True, text=True, timeout=5, check=False)
    if p.returncode != 0:
        return
    runtime = str(BASE / "openconnect-runtime/bin/openconnect")
    if not p.stdout.strip().startswith(runtime + " "):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def restore() -> None:
    if os.geteuid() != 0:
        raise ValueError("CISCO_ROOT_REQUIRED")
    saved = read_checkpoint()
    # Never restore to a service rebound to another physical device.
    if network_service_for_device(saved["interface"]) != saved["service"]:
        raise ValueError("CISCO_NETWORK_SERVICE_CHANGED")
    service = saved["service"]
    # A VPN can temporarily replace the default route. Verification must
    # target the original service directly, not whichever interface is primary.
    def matches() -> bool:
        details = command(NETWORKSETUP, "-getinfo", service)
        fields = dict(re.findall(r"(?m)^([^:\\n]+):\\s*([^\\n]+)$", details))
        original_mode = ("Manual Configuration" in details if saved["mode"] == "manual"
                         else "DHCP Configuration" in details)
        addr_match = (saved["mode"] != "manual" or
                      (fields.get("IP address"), fields.get("Subnet mask"),
                       fields.get("Router")) ==
                      (saved["ip"], saved["mask"], saved["gateway"]))
        dns_raw = command(NETWORKSETUP, "-getdnsservers", service).strip()
        current_dns = ([] if dns_raw.lower().startswith("there aren't any dns servers")
                       else [x.strip() for x in dns_raw.splitlines() if x.strip()])
        return original_mode and addr_match and current_dns == saved["dns"]

    if not matches():
        if saved["mode"] == "manual":
            command(NETWORKSETUP, "-setmanual", service,
                    saved["ip"], saved["mask"], saved["gateway"])
        else:
            command(NETWORKSETUP, "-setdhcp", service)
        command(NETWORKSETUP, "-setdnsservers", service,
                *(saved["dns"] if saved["dns"] else ["Empty"]))
        # SystemConfiguration can publish changed settings asynchronously.
        # Allow a short verified settle window, never erase the checkpoint
        # before the original IPv4/DNS values are observable.
        import time
        for _ in range(5):
            if matches():
                break
            time.sleep(1)
        else:
            raise ValueError("CISCO_NETWORK_RESTORE_UNVERIFIED")
    CHECKPOINT.unlink()
    print("CISCO_NETWORK_RESTORED_VERIFIED", flush=True)


def watch(parent_pid: int, deadline_seconds: int) -> None:
    """Independent root process: recover if Cisco exits uncleanly or times out.

    The watcher is launched with start_new_session=True. It never reads app
    credentials and only restores its own root-owned snapshot.
    """
    import signal
    import time
    if not (parent_pid > 1 and 10 <= deadline_seconds <= 600):
        raise ValueError("CISCO_NETWORK_WATCH_INVALID")
    until = time.monotonic() + deadline_seconds
    while time.monotonic() < until:
        if not CHECKPOINT.exists():
            return
        try:
            os.kill(parent_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(1)
    if not CHECKPOINT.exists():
        return
    # Timeout may have occurred while OpenConnect is still alive: request a
    # clean SIGTERM from its parent first, then forcibly restore network.
    try:
        os.kill(parent_pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    time.sleep(3)
    if CHECKPOINT.exists():
        # The launcher may have been SIGKILLed and left a root tunnel orphan.
        # Only stop a process verified to be our private OpenConnect binary.
        stop_orphaned_tunnel()
        time.sleep(2)
        if CHECKPOINT.exists():
            restore()


def main():
    try:
        if ((len(sys.argv) != 2 and len(sys.argv) != 4) or
            sys.argv[1] not in {"inspect", "snapshot", "restore", "watch"} or
            (sys.argv[1] == "watch") != (len(sys.argv) == 4)):
            raise ValueError("CISCO_NETWORK_ACTION_INVALID")
        if sys.argv[1] == "inspect":
            value = capture()
            print(json.dumps({"state": "CISCO_NETWORK_READY",
                              "interface": value["interface"],
                              "mode": value["mode"],
                              "has_default_gateway": bool(value["gateway"] or value["mode"] == "dhcp")}))
        elif sys.argv[1] == "snapshot":
            snapshot()
            print("CISCO_NETWORK_CHECKPOINT_SAVED")
        elif sys.argv[1] == "restore":
            restore()
        else:
            watch(int(sys.argv[2]), int(sys.argv[3]))
        return 0
    except (ValueError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        reason = str(error)
        if not re.fullmatch(r"CISCO_[A-Z0-9_]{3,70}", reason):
            reason = "CISCO_NETWORK_RECOVERY_FAILED"
        print(reason, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
