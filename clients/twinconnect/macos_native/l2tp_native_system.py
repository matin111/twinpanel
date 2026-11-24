#!/usr/bin/env python3
"""Root-owned macOS native L2TP/IPsec system VPN runner, without Apple signing.

Reads one authenticated tenant profile from stdin. The credentials never
appear in a command line, persistent config, log or guard state.
Requires a running independent launchd watchdog and Termalin route pinning.
Never reports Connected until native PPP, independent HTTPS egress and named
DNS/HTTPS over the installed system routes have all been verified.
"""
from __future__ import annotations

import importlib.util
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import time

ROOT = Path("/Library/PrivilegedHelperTools/TwinConnectL2TP")
NATIVE = ROOT / "twinconnect-l2tp-native"
GUARD = ROOT / "l2tp_management_route_guard.py"
PARSER = ROOT / "l2tp_native_preflight.py"
MAX_PROFILE = 4096
CONNECTION_WINDOW = 38

class Aborted(Exception):
    pass


def record_result(reason: str) -> None:
    """Persist only a sanitized reason, never profile or SAD contents."""
    root=Path("/private/var/run/twinconnect-l2tp-route-guard")
    try:
        info=root.lstat()
        if os.geteuid()!=0 or info.st_uid!=0 or not stat.S_ISDIR(info.st_mode) or info.st_mode&0o077:
            return
        fd=os.open(root/"last-result.json",os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"w") as out:
            json.dump({"reason":reason,"timestamp":time.time()},out)
    except OSError:
        pass


def safe_reply(reason: str, *, state: str = "error", vpn: bool = False) -> None:
    if not re.fullmatch(r"L2TP_[A-Z0-9_]{4,125}", reason):
        reason = "L2TP_OPERATION_FAILED"
    record_result(reason)
    print(json.dumps({"state": state, "reason": reason,
                      "vpn_connected": vpn}), flush=True)


def invoke(command: list[str], data: bytes | None = None,
           timeout: int = 15) -> tuple[int, str]:
    try:
        result = subprocess.run(command, input=data, capture_output=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return 255, ""
    return result.returncode, result.stdout[:2048].decode("utf-8", errors="replace").strip()


def guard(*args: str, timeout: int = 15) -> str:
    code, response = invoke(["/usr/bin/python3", str(GUARD), *args], timeout=timeout)
    answer = response.splitlines()[-1].strip() if response else ""
    if code or not re.fullmatch(r"L2TP_[A-Z0-9_]{4,125}", answer):
        raise ValueError(answer if answer.startswith("L2TP_") else
                         "L2TP_ROUTE_GUARD_REJECTED")
    return answer


def native(*args: str, data: bytes | None = None) -> dict:
    code, out = invoke([str(NATIVE), *args], data=data, timeout=12)
    try:
        reply = json.loads(out)
    except (TypeError, ValueError):
        raise ValueError("L2TP_NATIVE_HELPER_INVALID_RESULT") from None
    reason = reply.get("reason")
    if code or not isinstance(reason, str) or not reason.startswith("L2TP_"):
        raise ValueError(reason if isinstance(reason, str) and
                         re.fullmatch(r"L2TP_[A-Z0-9_]{4,125}", reason)
                         else "L2TP_NATIVE_HELPER_REJECTED")
    return reply


def parse_profile(source: bytes) -> dict:
    if not 10 < len(source) <= MAX_PROFILE:
        raise ValueError("L2TP_PROFILE_INVALID_SIZE")
    try:
        data = json.loads(source)
    except (ValueError, UnicodeError):
        raise ValueError("L2TP_PROFILE_INVALID_JSON") from None
    # Load only the reviewed, root-owned validation module.
    spec = importlib.util.spec_from_file_location("l2tp_native_preflight", PARSER)
    if spec is None or spec.loader is None:
        raise ValueError("L2TP_PROFILE_VALIDATOR_MISSING")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.inspect_profile(data)
    return data


def resolved_endpoint(host: str) -> str:
    try:
        choices = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM)
        addresses = sorted({ipaddress.IPv4Address(item[4][0]) for item in choices})
    except (ValueError, OSError):
        raise ValueError("L2TP_REMOTE_ENDPOINT_UNRESOLVED") from None
    if not addresses or any(not item.is_global for item in addresses):
        raise ValueError("L2TP_REMOTE_ENDPOINT_UNSAFE")
    # Native profile is explicitly pinned to the same IP as the /32 bypass,
    # so DNS cannot silently resolve a different server after VPN starts.
    return str(addresses[0])


def verify_native_link() -> bool:
    try:
        return native("status").get("reason") == "L2TP_NATIVE_LINK_CONNECTED_UNROUTED"
    except ValueError:
        return False


def detected_ppp() -> str | None:
    result = subprocess.run(["/sbin/ifconfig", "-l"], capture_output=True,
                            text=True, timeout=5, check=False)
    if result.returncode:
        return None
    detected = []
    for interface in result.stdout.split():
        if not re.fullmatch(r"ppp[0-9]{1,4}", interface):
            continue
        r = subprocess.run(["/sbin/ifconfig", interface], capture_output=True,
                           text=True, timeout=5, check=False)
        if r.returncode == 0 and re.search(
                r"(?m)^\s*inet\s+[0-9.]+\s+-->\s+[0-9.]+", r.stdout):
            detected.append(interface)
    return detected[0] if len(detected) == 1 else None


def check_probe(interface: str, destination: str) -> None:
    if guard("probe-host", interface, destination) != "L2TP_PROBE_HOST_ACTIVE":
        raise ValueError("L2TP_PROBE_UNAVAILABLE")
    reason = ""
    try:
        reason = guard("verify-probe", timeout=15)
        if reason != "L2TP_PROBE_EGRESS_VERIFIED":
            raise ValueError("L2TP_PROBE_NOT_VERIFIED")
    finally:
        if guard("rollback-probe", timeout=15) != "L2TP_PROBE_ROLLBACK_VERIFIED":
            raise ValueError("L2TP_PROBE_ROLLBACK_UNVERIFIED")


def verify_ipsec_peer(endpoint: str) -> bool:
    """Check the two mature ESP transport SAs for the selected server.
    The SAD output can include key material; it never leaves this function.
    """
    try:
        result = subprocess.run(["/usr/sbin/setkey", "-D"], capture_output=True,
                                text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return False
    if result.returncode or len(result.stdout)>262144:
        return False
    pairs=set()
    for record in re.split(r"(?m)\n(?=\S)",result.stdout.strip()):
        lines=record.splitlines()
        if not lines:
            continue
        match=re.fullmatch(r"\s*([0-9.]+)(?:\[[0-9]+\])?\s+([0-9.]+)(?:\[[0-9]+\])?\s*",lines[0])
        if not match:
            continue
        source,dest=match.groups()
        try:
            source=str(ipaddress.IPv4Address(source))
            dest=str(ipaddress.IPv4Address(dest))
        except ValueError:
            continue
        body="\n".join(lines[1:])
        if (not re.search(r"(?m)^\s+esp\s",body) or
                not re.search(r"\bmode=transport\b",body) or
                not re.search(r"\bstate=mature\b",body)):
            continue
        pairs.add((source,dest))
    return any(dest==endpoint and source!=endpoint and (dest,source) in pairs
               for source,dest in pairs)


def kill_switch_control():
    import importlib.util
    import stat
    state=Path("/private/var/run/twinconnect-killswitch-control")
    try:
        state_info=state.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(state_info.st_mode) or state_info.st_uid!=0 or state_info.st_mode & 0o077:
        raise ValueError("KS_STATE_UNTRUSTED")
    try:
        lease=(state/"lease.json").lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(lease.st_mode) or lease.st_uid!=0 or lease.st_mode & 0o077:
        raise ValueError("KS_LEASE_UNTRUSTED")
    root=Path("/Library/PrivilegedHelperTools/TwinConnectKillSwitchControl")
    script=root/"unsigned_killswitch_console_control.py"
    for path,kind in ((root,stat.S_ISDIR),(script,stat.S_ISREG)):
        info=path.lstat()
        if info.st_uid!=0 or info.st_mode & 0o022 or not kind(info.st_mode):
            raise ValueError("KS_CONTROL_UNTRUSTED")
    spec=importlib.util.spec_from_file_location("tc_installed_ks_control",script)
    if spec is None or spec.loader is None:
        raise ValueError("KS_CONTROL_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def full_connection(payload: dict,raw=None) -> None:
    if raw is None:
        raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode("utf-8")
    digest=hashlib.sha256(raw).hexdigest()
    control=kill_switch_control()
    protected=None
    if control:
        try:
            protected=control.begin_reconnect(raw.decode("utf-8"),"l2tp")
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            raise ValueError("L2TP_KS_RECONNECT_NOT_AUTHORIZED") from None
        if not protected:
            raise ValueError("L2TP_KS_RECONNECT_NOT_AUTHORIZED")
    try:
        connect_reviewed(payload,digest,control,protected)
    finally:
        if protected:
            try:
                control.abort_reconnect("l2tp")
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
                pass


def connect_reviewed(payload,digest,control,protected):
    if guard("preflight") != "L2TP_MANAGEMENT_PRECHECK_READY":
        raise ValueError("L2TP_PREFLIGHT_FAILED")
    address = protected["ip"] if protected else resolved_endpoint(payload["server"])
    fixed = {**payload, "server": address}
    blob = json.dumps(fixed, separators=(",", ":")).encode("utf-8")
    if guard("arm", address,str(os.getpid()),digest) != "L2TP_MANAGEMENT_PIN_ARMED":
        raise ValueError("L2TP_MANAGEMENT_PIN_FAILED")
    # Root-only native API will not persist PPP password or IPsec PSK.
    profile = native("capabilities")
    if profile.get("reason") == "L2TP_NATIVE_SERVICE_NOT_CONFIGURED":
        prepared = native("prepare", data=blob)
        if prepared.get("reason") != "L2TP_SERVICE_PREPARED_NO_VPN_CONNECTED":
            raise ValueError("L2TP_PREPARE_FAILED")
    elif profile.get("reason") != "L2TP_NATIVE_SERVICE_CONFIGURED":
        raise ValueError("L2TP_SERVICE_UNAVAILABLE")
    started = native("start", data=blob)
    if started.get("reason") != "L2TP_NATIVE_HANDSHAKE_STARTED_NOT_CONNECTED":
        raise ValueError("L2TP_START_FAILED")
    deadline = time.monotonic() + CONNECTION_WINDOW
    interface = None
    while time.monotonic() < deadline:
        time.sleep(1)
        if verify_native_link():
            interface = detected_ppp()
            if interface:
                break
    if interface is None:
        raise ValueError("L2TP_PPP_HANDSHAKE_TIMEOUT")
    # PPP can become visible slightly before both mature SAs are observable.
    # Wait briefly within the existing watchdog window, never bypass the check.
    verified=False
    for _ in range(4):
        if verify_ipsec_peer(address):
            verified=True
            break
        time.sleep(0.5)
    if not verified:
        raise ValueError("L2TP_IPSEC_ENDPOINT_MISMATCH")
    if protected:
        try:
            control.attach_l2tp_reconnect(os.getpid(),interface,digest)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            raise ValueError("L2TP_KS_PEER_UNVERIFIED") from None
    for group in (("1.1.1.1","1.0.0.1"),("8.8.8.8","8.8.4.4")):
        for destination in group:
            try:
                check_probe(interface,destination)
                break
            except ValueError as exc:
                if str(exc)!="L2TP_PROBE_ROUTE_PREEXISTS" or destination==group[-1]:
                    raise
    if guard("activate", interface, timeout=30) != "L2TP_SYSTEM_IPV4_CONNECTED":
        raise ValueError("L2TP_FULL_ROUTE_UNVERIFIED")
    if protected:
        try:
            control.complete_reconnect(os.getpid(),interface)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            raise ValueError("L2TP_KS_RECONNECT_UNVERIFIED") from None
    safe_reply("L2TP_SYSTEM_IPV4_CONNECTED", state="connected", vpn=True)
    # Continuous heartbeat preserves the lease. A crash or a closed window
    # causes the independently installed watchdog to roll everything back.
    while True:
        time.sleep(12)
        if guard("heartbeat") != "L2TP_SYSTEM_IPV4_CONNECTED":
            raise ValueError("L2TP_LEASE_LOST")


def main() -> int:
    if sys.platform != "darwin" or os.geteuid() != 0:
        safe_reply("L2TP_MACOS_ROOT_REQUIRED")
        return 2
    if sys.argv[1:] != ["system"]:
        safe_reply("L2TP_ACTION_INVALID")
        return 2
    for component in (NATIVE, GUARD, PARSER):
        try:
            stat = component.lstat()
            if component.is_symlink() or not component.is_file() or (
                    stat.st_uid != 0 or stat.st_mode & 0o022):
                safe_reply("L2TP_ROOT_HELPER_UNTRUSTED")
                return 2
        except OSError:
            safe_reply("L2TP_ROOT_HELPER_MISSING")
            return 2
    # signal handlers run in main thread so disconnect can always restore.
    def terminate(_signum, _frame):
        raise Aborted()
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        raw=os.read(0, MAX_PROFILE + 1)
        payload = parse_profile(raw)
        full_connection(payload,raw)
        return 0
    except Aborted:
        safe_reply("L2TP_SYSTEM_DISCONNECTED", state="disconnected")
        return 0
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        safe_reply(str(exc))
        return 1
    finally:
        # Never let a failed connection retain routing privileges.
        try:
            state=Path("/private/var/run/twinconnect-l2tp-route-guard/state.json")
            current=json.loads(state.read_text()) if state.exists() else {}
            if current.get("worker_pid")==os.getpid():
                invoke(["/usr/bin/python3", str(GUARD), "stop"], timeout=17)
        except Exception:
            pass  # watchdog still has a root-owned deadline


if __name__ == "__main__":
    raise SystemExit(main())
