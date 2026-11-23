#!/usr/bin/env python3
"""Root-owned, local-console-only TwinConnect TUN control daemon.

Experimental: never install or run on a remote/cloud Mac. No auto-installer.
The UNIX socket requires peer UID == active /dev/console user. Credentials
are transferred as JSON over the local socket, never via argv or logs.
A separate supervised/watchdog recovery mechanism is still required before
general release. The daemon does not claim a verified VPN connection.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import platform
import pwd
import secrets
import select
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.request

from unsigned_tun_policy import (TRUSTED_ROOT, trusted_root_file,
                                 validate_full_tun_config)
from openvpn_profile_review import review as review_openvpn

SOCKET_PATH = Path("/var/run/twinconnect-tun.sock")
ENGINE = TRUSTED_ROOT / "sing-box"
APPROVAL = TRUSTED_ROOT / "local-console-approval"
WATCHDOG = TRUSTED_ROOT / "unsigned_tun_watchdog.py"
OPENVPN = TRUSTED_ROOT / "openvpn/bin/openvpn"
OPENVPN_REVIEW = TRUSTED_ROOT / "openvpn_profile_review.py"
MAX_REQUEST = 262144
MAX_SESSION = 600
VPS_SESSION = 45


def session_limit() -> int:
    """VPS experiments must expire even if the GUI never sends Stop."""
    try:
        if APPROVAL.read_text(encoding="ascii").strip() == "VPS_OOB_CONSOLE_45_SECONDS":
            return VPS_SESSION
    except OSError:
        pass
    return MAX_SESSION



def allowed_uid(peer_uid: int, console_uid: int) -> bool:
    return console_uid > 0 and peer_uid == console_uid


def unix_peer_uid(conn: socket.socket) -> int:
    """Query kernel-authenticated UID; macOS Python 3.9 omits getpeereid()."""
    if sys.platform != "darwin":
        raise ValueError("DARWIN_UNIX_PEER_REQUIRED")
    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    func = libc.getpeereid
    func.argtypes = [ctypes.c_int,
                     ctypes.POINTER(ctypes.c_uint),
                     ctypes.POINTER(ctypes.c_uint)]
    func.restype = ctypes.c_int
    uid = ctypes.c_uint()
    gid = ctypes.c_uint()
    if func(conn.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
        raise OSError(ctypes.get_errno(), "UNIX_PEER_CREDENTIALS_UNAVAILABLE")
    return uid.value


def authorized_peer(conn: socket.socket) -> bool:
    peer_uid = unix_peer_uid(conn)
    return allowed_uid(peer_uid, os.stat("/dev/console").st_uid)


def daemon_preflight() -> None:
    if platform.system() != "Darwin" or os.geteuid() != 0:
        raise ValueError("ROOT_MACOS_REQUIRED")
    if any(os.environ.get(k) for k in ("SSH_CONNECTION", "SSH_TTY",
                                       "SSH_CLIENT", "TWINCONNECT_REMOTE_VPS")):
        raise ValueError("REMOTE_SESSION_REFUSED")
    if not trusted_root_file(ENGINE) or not os.access(ENGINE, os.X_OK):
        raise ValueError("TRUSTED_ENGINE_NOT_INSTALLED")
    if not trusted_root_file(OPENVPN_REVIEW):
        raise ValueError("TRUSTED_OPENVPN_REVIEW_NOT_INSTALLED")
    if not trusted_root_file(WATCHDOG):
        raise ValueError("TRUSTED_WATCHDOG_NOT_INSTALLED")
    if not trusted_root_file(APPROVAL):
        raise ValueError("LOCAL_CONSOLE_APPROVAL_MISSING")
    approval = APPROVAL.read_text(encoding="ascii").strip()
    if approval not in ("LOCAL_MAC_WITH_RECOVERY", "VPS_OOB_CONSOLE_45_SECONDS"):
        raise ValueError("LOCAL_CONSOLE_APPROVAL_INVALID")
    # Fail closed if there is no signed-in physical console owner.
    if os.stat("/dev/console").st_uid <= 0:
        raise ValueError("NO_LOCAL_CONSOLE_OWNER")
    # Not proof that networking is recoverable. Administrator must install
    # only with working physical console or equivalent out-of-band access.


def observe_route() -> dict:
    """Read-only macOS route observation, not proof of tunneled egress.

    The selected route is merely observed, so system_vpn_verified remains false.
    The daemon never changes routes or DNS to perform this check.
    """
    if platform.system() != "Darwin":
        return {"route_state": "not_macos"}
    try:
        result = subprocess.run(
            ["/sbin/route", "-n", "get", "1.1.1.1"],
            check=False, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return {"route_state": "unavailable"}
    if result.returncode != 0 or len(result.stdout) > 16384:
        return {"route_state": "unavailable"}
    interface = None
    for line in result.stdout.splitlines():
        key, sep, value = line.strip().partition(":")
        if sep and key == "interface":
            interface = value.strip()
            break
    if not interface or not interface.isascii():
        return {"route_state": "unavailable"}
    if interface.startswith("utun") and interface[4:].isdigit():
        return {"route_state": "utun_route_observed_unverified"}
    return {"route_state": "not_utun_route"}


def probe_system_https() -> dict:
    """Probe HTTPS via macOS system networking without proxy env overrides.

    This checks the OS transport, not a loopback SOCKS proxy. The route must
    already point at utun; DNS and public exit IP remain unverified here.
    No profile credentials or response contents are persisted.
    """
    if observe_route().get("route_state") != "utun_route_observed_unverified":
        return {"https_state": "tun_route_not_observed"}
    request = urllib.request.Request(
        "https://www.cloudflare.com/cdn-cgi/trace",
        headers={"User-Agent": "TwinConnect-TUN-Health/1.0"})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as reply:
            if reply.status != 200:
                return {"https_state": "http_status_failed"}
            raw = reply.read(4097)
        if len(raw) > 4096:
            return {"https_state": "invalid_response"}
        rows = {}
        for line in raw.decode("utf-8", errors="strict").splitlines():
            key, sep, value = line.partition("=")
            if sep and key in ("ip", "warp", "loc"):
                rows[key] = value
        if "ip" not in rows or not (3 <= len(rows["ip"]) <= 64):
            return {"https_state": "invalid_response"}
        import ipaddress
        if not ipaddress.ip_address(rows["ip"]).is_global:
            return {"https_state": "invalid_response"}
        return {"https_state": "system_https_reachable",
                "observed_exit_ip": rows["ip"],
                "system_vpn_verified": False}
    except (OSError, ValueError, UnicodeError, TimeoutError):
        return {"https_state": "unreachable"}


class Session:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.watchdog: subprocess.Popen | None = None
        self.config: Path | None = None
        self.owner: int | None = None
        self.started: float | None = None

    def console_owner_present(self) -> bool:
        """Kill the tunnel when console ownership changes or user logs out."""
        if self.owner is None:
            return True
        try:
            return os.stat("/dev/console").st_uid == self.owner
        except OSError:
            return False

    def cleanup(self) -> None:
        with self.lock:
            child = self.process
            # Clear state even if kill fails; do not leave credential files.
            try:
                if child is not None and child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait(timeout=5)
                    except ProcessLookupError:
                        pass
            finally:
                if self.config is not None:
                    self.config.unlink(missing_ok=True)
                self.process = None
                self.watchdog = None
                self.config = None
                self.owner = None
                self.started = None

    def status(self) -> dict:
        with self.lock:
            if self.process is not None:
                if self.process.poll() is not None or (
                    self.watchdog is not None and self.watchdog.poll() is not None
                ) or (
                    self.started is not None and
                    time.monotonic() - self.started > session_limit()
                ) or not self.console_owner_present():
                    self.cleanup()
            status = {
                "state": "engine_running_unverified" if self.process else "stopped",
                "system_vpn_verified": False,
                "owner_present": self.owner is not None,
                "maximum_session_seconds": session_limit(),
            }
            if self.process is not None:
                status.update(observe_route())
            return status

    def start(self, uid: int, profile: object) -> dict:
        with self.lock:
            if self.status()["state"] != "stopped":
                raise ValueError("TUN_ALREADY_RUNNING")
            if not isinstance(profile, dict):
                raise ValueError("TUN_CONFIG_NOT_OBJECT")
            use_openvpn = profile.get("mode") == "openvpn"
            if use_openvpn:
                if set(profile) != {"mode", "profile"} or not isinstance(
                        profile.get("profile"), str):
                    raise ValueError("OPENVPN_PROFILE_INVALID")
                if not trusted_root_file(OPENVPN) or not os.access(OPENVPN, os.X_OK):
                    raise ValueError("TRUSTED_OPENVPN_NOT_INSTALLED")
                reviewed = review_openvpn(profile["profile"])
                lines = list(reviewed["directives"])
                if "remote-cert-tls server" not in lines:
                    raise ValueError("OPENVPN_CERTIFICATE_ROLE_REQUIRED")
                for kind, value in reviewed["inline"].items():
                    lines.extend(["<" + kind + ">", value.rstrip("\n"),
                                  "</" + kind + ">"])
                encoded = ("\n".join(lines) + "\n").encode("utf-8")
                engine = OPENVPN
            else:
                encoded = json.dumps(profile, separators=(",", ":")).encode("utf-8")
                engine = ENGINE
            if len(encoded) > MAX_REQUEST - 1024:
                raise ValueError("TUN_CONFIG_TOO_LARGE")
            # Existing utun routes may belong to another VPN: do not mistake
            # that routing for TwinConnect's tunnel.
            if observe_route()["route_state"] == "utun_route_observed_unverified":
                raise ValueError("EXISTING_TUN_ROUTE_AMBIGUOUS")
            path = TRUSTED_ROOT / ("active-" + secrets.token_hex(16) + (".ovpn" if use_openvpn else ".json"))
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(encoded)
                if use_openvpn:
                    command = [str(engine), "--config", str(path),
                               "--script-security", "1", "--auth-nocache",
                               # Server-pushed routes and DNS are prohibited
                               # until physical-console recovery and an
                               # independently reviewed route policy exist.
                               "--route-nopull"]
                else:
                    validate_full_tun_config(path)
                    subprocess.run([str(engine), "check", "-c", str(path)],
                                   check=True, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=20)
                    command = [str(engine), "run", "-c", str(path)]
                child = subprocess.Popen(command,
                                         stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL,
                                         start_new_session=True)
                self.process = child
                self.config = path
                self.owner = uid
                self.started = time.monotonic()
                # Engine must never run without independent daemon-death
                # supervision. Wait for the watchdog to install its Darwin
                # NOTE_EXIT kqueue filter before replying success.
                watcher = subprocess.Popen(
                    [sys.executable, str(WATCHDOG), "--parent",
                     str(os.getpid()), "--engine", str(child.pid),
                     "--seconds", str(session_limit())],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True)
                self.watchdog = watcher
                ready, _, _ = select.select([watcher.stdout], [], [], 3.0)
                if not ready or watcher.stdout.readline() != b"WATCHDOG_READY\n":
                    self.cleanup()
                    raise ValueError("TUN_WATCHDOG_START_FAILED")
                watcher.stdout.close()
                # The engine process existing is insufficient. Verify that
                # macOS installed a utun route, with a short bounded startup
                # window; never treat this as proof of remote HTTPS egress.
                route_observed = False
                for _ in range(12):
                    if child.poll() is not None or watcher.poll() is not None:
                        break
                    if observe_route()["route_state"] == "utun_route_observed_unverified":
                        route_observed = True
                        break
                    time.sleep(0.25)
                if not route_observed:
                    raise ValueError("TUN_ROUTE_NOT_ESTABLISHED")
                return self.status()
            except BaseException:
                self.cleanup()
                path.unlink(missing_ok=True)
                raise

    def stop(self, uid: int) -> dict:
        with self.lock:
            if self.owner is not None and self.owner != uid:
                raise ValueError("TUN_OWNER_MISMATCH")
            self.cleanup()
            return self.status()


def decode_request(raw: bytes) -> dict:
    if not 0 < len(raw) <= MAX_REQUEST:
        raise ValueError("TUN_REQUEST_SIZE_INVALID")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("action") not in (
        "status", "probe", "start", "stop"):
        raise ValueError("TUN_REQUEST_ACTION_INVALID")
    return value


def reply(conn: socket.socket, result: dict) -> None:
    conn.sendall(json.dumps(result, separators=(",", ":")).encode("utf-8") + b"\n")


def handle(conn: socket.socket, session: Session) -> None:
    conn.settimeout(5)
    try:
        if not authorized_peer(conn):
            raise ValueError("TUN_CONSOLE_OWNER_REQUIRED")
        uid = unix_peer_uid(conn)
        data = bytearray()
        while len(data) <= MAX_REQUEST:
            chunk = conn.recv(min(8192, MAX_REQUEST + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if b"\n" in chunk:
                break
        if len(data) > MAX_REQUEST or b"\n" not in data:
            raise ValueError("TUN_REQUEST_SIZE_INVALID")
        request = decode_request(bytes(data.split(b"\n", 1)[0]))
        action = request["action"]
        if action == "status":
            result = session.status()
        elif action == "probe":
            result = session.status()
            if result["state"] == "engine_running_unverified":
                result.update(probe_system_https())
            else:
                result["https_state"] = "engine_not_running"
        elif action == "start":
            result = session.start(uid, request.get("config"))
        else:
            result = session.stop(uid)
        reply(conn, result)
    except (ValueError, OSError, subprocess.SubprocessError,
            UnicodeError, json.JSONDecodeError):
        try:
            reply(conn, {"state": "rejected", "system_vpn_verified": False})
        except OSError:
            pass


def main() -> int:
    daemon_preflight()
    if SOCKET_PATH.exists() or SOCKET_PATH.is_symlink():
        raise ValueError("SOCKET_PATH_ALREADY_EXISTS")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    session = Session()
    server.bind(str(SOCKET_PATH))
    os.chmod(SOCKET_PATH, 0o666)  # getpeereid + console UID is the authorization.
    server.listen(4)
    server.settimeout(1.0)
    stop = threading.Event()

    def request_shutdown(_sig, _frame):
        stop.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    try:
        while not stop.is_set():
            session.status()  # reap, expiry, and console logout cleanup
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            with conn:
                handle(conn, session)
    finally:
        session.cleanup()
        server.close()
        SOCKET_PATH.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print(str(error) if str(error).isupper() else "TUN_DAEMON_FAILED",
              file=sys.stderr)
        raise SystemExit(1)