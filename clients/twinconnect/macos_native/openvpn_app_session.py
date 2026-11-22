#!/usr/bin/env python3
"""Root-owned, time-bounded macOS OpenVPN session for TwinConnect.

Commands authorized by sudoers: start (profile over stdin), status, stop.
Internal worker retains an authenticated OpenVPN tunnel WITHOUT importing
default routes or DNS; it is not proof of system-wide VPN egress.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time

from openvpn_profile_review import review, MAX_PROFILE_BYTES

BASE = Path("/private/var/run/twinconnect-openvpn-app")
STATE = BASE / "state.json"
CONFIG = BASE / "session.ovpn"
LOG = BASE / "openvpn.log"
STOP = BASE / "stop"
LOCK = Path("/private/var/run/twinconnect-openvpn-app.lock")
MAX_SESSION_SECONDS = 900
START_TIMEOUT_SECONDS = 35
ENGINES = (Path("/usr/local/opt/openvpn/sbin/openvpn"),
           Path("/opt/homebrew/opt/openvpn/sbin/openvpn"))
SUCCESS = b"Initialization Sequence Completed"
FAILURES = (("AUTH_FAILED", "OPENVPN_AUTH_FAILED"),
            ("VERIFY ERROR", "OPENVPN_CERT_VERIFY_FAILED"),
            ("TLS Error", "OPENVPN_TLS_FAILED"),
            ("Options error", "OPENVPN_OPTIONS_ERROR"),
            ("Cannot open TUN", "OPENVPN_UTUN_UNAVAILABLE"))


def output(state: str) -> None:
    print(json.dumps({"state": state, "system_vpn_verified": False}),
          flush=True)


def default_route() -> tuple[str, str] | None:
    try:
        r = subprocess.run(["/sbin/route", "-n", "get", "default"],
                           capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    values = {}
    for line in r.stdout.splitlines():
        k, sep, v = line.strip().partition(":")
        if sep and k in ("gateway", "interface"):
            values[k] = v.strip()
    if r.returncode or not values.get("gateway") or not values.get("interface"):
        return None
    return (values["gateway"], values["interface"])


def safe_config(raw: bytes) -> bytes:
    if len(raw) > MAX_PROFILE_BYTES or not raw:
        raise ValueError("OPENVPN_PROFILE_REJECTED")
    result = review(raw.decode("utf-8", errors="strict"))
    if "remote-cert-tls server" not in result["directives"]:
        raise ValueError("OPENVPN_PROFILE_REJECTED")
    lines = list(result["directives"])
    for tag, body in result["inline"].items():
        lines.extend(["<" + tag + ">", body.rstrip("\n"), "</" + tag + ">"])
    return ("\n".join(lines) + "\n").encode()


def write_private(path: Path, payload: bytes) -> None:
    with os.fdopen(os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC |
                          os.O_NOFOLLOW, 0o600), "wb") as f:
        f.write(payload)


def locked():
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def read_state() -> dict:
    try:
        value = json.loads(STATE.read_text())
        if isinstance(value, dict):
            return value
    except (OSError, ValueError, UnicodeError):
        pass
    return {}


def pid_running(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def status() -> str:
    data = read_state()
    state = data.get("state", "stopped")
    if state in ("starting", "tunnel_established_unrouted",
                 "tunnel_egress_verified_unrouted"):
        if not pid_running(data.get("worker_pid")):
            return "OPENVPN_WORKER_EXITED"
        if time.time() >= data.get("deadline", 0):
            return "OPENVPN_SESSION_EXPIRED"
    return state


def cleanup(*, preserve_state: bool = False) -> None:
    # State directory is root-owned and never accessible to the app.
    for p in ((CONFIG, LOG, STOP) if preserve_state else
              (CONFIG, LOG, STOP, STATE)):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def stop_openvpn(child: subprocess.Popen) -> None:
    if child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)


def state_write(state: str, worker_pid: int, deadline: float,
                interface: str | None = None) -> None:
    # Never include profile, tokens, endpoints or private key in status.
    payload = {"state": state, "worker_pid": worker_pid, "deadline": deadline}
    if interface is not None:
        payload["interface"] = interface
    write_private(STATE, json.dumps(payload).encode())


def utun_interfaces() -> set[str]:
    """Observe utun interfaces without touching default routing."""
    try:
        result = subprocess.run(["/sbin/ifconfig", "-l"],
                                capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if result.returncode:
        return set()
    return {name for name in result.stdout.split()
            if name.startswith("utun") and name[4:].isdigit()}


def tunnel_https_probe(interface: str) -> bool:
    """Bind one HTTPS request to the new utun; do not add routes or DNS."""
    if interface not in utun_interfaces():
        return False
    try:
        result = subprocess.run([
            "/usr/bin/curl", "--interface", "if!" + interface,
            "--noproxy", "*", "--connect-timeout", "5",
            "--max-time", "10", "--fail", "--silent",
            "https://1.1.1.1/cdn-cgi/trace",
        ], capture_output=True, timeout=12)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0 or len(result.stdout) > 4096:
        return False
    return any(line.startswith(b"ip=") and 6 <= len(line) <= 68
               for line in result.stdout.splitlines())


def worker() -> int:
    source = CONFIG
    engine = next((p for p in ENGINES if p.is_file() and os.access(p, os.X_OK)), None)
    before = default_route()
    before_utun = utun_interfaces()
    deadline = time.time() + MAX_SESSION_SECONDS
    if engine is None or before is None or not source.is_file():
        state_write("OPENVPN_ENGINE_OR_ROUTE_MISSING", os.getpid(), deadline)
        return 1
    child = None
    try:
        with open(LOG, "ab", buffering=0) as log:
            child = subprocess.Popen([
                str(engine), "--config", str(source), "--route-nopull",
                "--script-security", "1", "--auth-nocache", "--verb", "3"
            ], stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True)
            handshake = False
            egress_checked = False
            while time.time() < deadline and not STOP.exists():
                if default_route() != before:
                    state_write("OPENVPN_ROUTE_CHANGED_STOPPED",
                                os.getpid(), deadline)
                    return 2
                if child.poll() is not None:
                    state_write("OPENVPN_ENGINE_EXITED",
                                os.getpid(), deadline)
                    return 2
                # Read only fixed-size tail; no raw log is exposed to app.
                try:
                    with open(LOG, "rb") as f:
                        f.seek(max(0, f.seek(0, os.SEEK_END) - 65536))
                        log_bytes = f.read()
                except OSError:
                    log_bytes = b""
                if not handshake:
                    if SUCCESS in log_bytes:
                        handshake = True
                        added = sorted(utun_interfaces() - before_utun)
                        state_write("tunnel_established_unrouted",
                                    os.getpid(), deadline,
                                    added[0] if len(added) == 1 else None)
                    else:
                        for pattern, reason in FAILURES:
                            if pattern.encode() in log_bytes:
                                state_write(reason, os.getpid(), deadline)
                                return 2
                if handshake and not egress_checked:
                    egress_checked = True
                    added = sorted(utun_interfaces() - before_utun)
                    if len(added) == 1 and tunnel_https_probe(added[0]):
                        state_write("tunnel_egress_verified_unrouted",
                                    os.getpid(), deadline, added[0])
                time.sleep(0.5)
            if not handshake and not STOP.exists():
                state_write("OPENVPN_HANDSHAKE_TIMEOUT",
                            os.getpid(), deadline)
        return 0
    finally:
        # On expiry, engine failure and user-requested stop alike, ask the
        # independent privileged route guard to restore its owned routes
        # BEFORE removing the utun. This also covers GUI crashes.
        if child is not None:
            guard_state = Path(
                "/private/var/run/twinconnect-full-route-guard/state.json")
            if guard_state.exists():
                rollback_routes_before_stop()
                # The independent watchdog may need another pass. Keep the
                # transport alive briefly rather than destroying the interface
                # before its routes have been rolled back.
                recovery_deadline = time.monotonic() + 65
                while guard_state.exists() and time.monotonic() < recovery_deadline:
                    time.sleep(1)
                    rollback_routes_before_stop()
            stop_openvpn(child)
        cleanup(preserve_state=True)


def start() -> int:
    raw = sys.stdin.buffer.read(MAX_PROFILE_BYTES + 1)
    try:
        prepared = safe_config(raw)
    except (ValueError, UnicodeError):
        output("OPENVPN_PROFILE_REJECTED")
        return 2
    lock = locked()
    try:
        if status() in ("starting", "tunnel_established_unrouted",
                        "tunnel_egress_verified_unrouted"):
            output("OPENVPN_ALREADY_RUNNING")
            return 2
        # A dead worker may leave files; never wipe an active process's data.
        data = read_state()
        if pid_running(data.get("worker_pid")):
            output("OPENVPN_PREVIOUS_WORKER_ACTIVE")
            return 2
        BASE.mkdir(mode=0o700, exist_ok=True)
        if BASE.is_symlink() or BASE.stat().st_uid != 0:
            output("OPENVPN_PRIVATE_DIR_UNTRUSTED")
            return 2
        cleanup()
        write_private(CONFIG, prepared)
        # Worker is a separate root process with a bounded lifetime.
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                                  "worker"], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        state_write("starting", child.pid, time.time() + MAX_SESSION_SECONDS)
    finally:
        os.close(lock)
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        current = status()
        if current != "starting":
            output(current)
            return 0 if current in ("tunnel_established_unrouted",
                                    "tunnel_egress_verified_unrouted") else 1
        time.sleep(0.5)
    STOP.touch(mode=0o600)
    output("OPENVPN_HANDSHAKE_TIMEOUT")
    return 1


def rollback_routes_before_stop() -> bool:
    """Never tear down OpenVPN while a managed full-route trial is active.

    The root route watchdog owns the route state. Its lock serializes route
    rollback with its daemon; this worker may only ask it to roll back.
    If rollback cannot be verified, preserve the tunnel and report failure.
    """
    guard_state = Path("/private/var/run/twinconnect-full-route-guard/state.json")
    if not guard_state.exists():
        return True
    guard_script = Path(
        "/Library/PrivilegedHelperTools/TwinConnectFullRouteGuard/"
        "macos_openvpn_full_route_guard.py")
    if not guard_script.is_file():
        return False
    try:
        result = subprocess.run(
            ["/usr/bin/python3", str(guard_script), "rollback"],
            capture_output=True, text=True, timeout=12, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return (result.returncode == 0 and
            result.stdout.strip() == "ROLLBACK_VERIFIED" and
            not guard_state.exists())


def stop() -> int:
    # All stop paths must restore owned routes before removing the tunnel.
    # A failure leaves the tunnel alive so management access is not stranded.
    if not rollback_routes_before_stop():
        output("OPENVPN_ROUTE_ROLLBACK_REQUIRED")
        return 1
    current = status()
    if current not in ("starting", "tunnel_established_unrouted",
                        "tunnel_egress_verified_unrouted"):
        output("stopped")
        return 0
    STOP.touch(mode=0o600)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if not pid_running(read_state().get("worker_pid")):
            output("stopped")
            return 0
        time.sleep(0.25)
    output("OPENVPN_STOP_PENDING")
    return 1


def main() -> int:
    if platform.system() != "Darwin" or os.geteuid() != 0:
        output("MACOS_ROOT_REQUIRED")
        return 2
    if len(sys.argv) != 2 or sys.argv[1] not in (
            "start", "stop", "status", "worker"):
        output("OPENVPN_INVALID_ACTION")
        return 2
    action = sys.argv[1]
    if action == "worker":
        return worker()
    if action == "start":
        return start()
    if action == "stop":
        return stop()
    output(status())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
