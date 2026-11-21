#!/usr/bin/env python3
"""Root-owned, local-console-only TwinConnect TUN control daemon.

Experimental: never install or run on a remote/cloud Mac. No auto-installer.
The UNIX socket requires peer UID == active /dev/console user. Credentials
are transferred as JSON over the local socket, never via argv or logs.
A separate supervised/watchdog recovery mechanism is still required before
general release. The daemon does not claim a verified VPN connection.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import pwd
import secrets
import signal
import socket
import stat
import subprocess
import sys
import threading
import time

from unsigned_tun_policy import (TRUSTED_ROOT, trusted_root_file,
                                 validate_full_tun_config)

SOCKET_PATH = Path("/var/run/twinconnect-tun.sock")
ENGINE = TRUSTED_ROOT / "sing-box"
APPROVAL = TRUSTED_ROOT / "local-console-approval"
MAX_REQUEST = 262144
MAX_SESSION = 600


def allowed_uid(peer_uid: int, console_uid: int) -> bool:
    return console_uid > 0 and peer_uid == console_uid


def authorized_peer(conn: socket.socket) -> bool:
    # getpeereid() is available on Darwin UNIX-domain sockets.
    if not hasattr(conn, "getpeereid"):
        return False
    peer_uid, _ = conn.getpeereid()
    return allowed_uid(peer_uid, os.stat("/dev/console").st_uid)


def daemon_preflight() -> None:
    if platform.system() != "Darwin" or os.geteuid() != 0:
        raise ValueError("ROOT_MACOS_REQUIRED")
    if any(os.environ.get(k) for k in ("SSH_CONNECTION", "SSH_TTY",
                                       "SSH_CLIENT", "TWINCONNECT_REMOTE_VPS")):
        raise ValueError("REMOTE_SESSION_REFUSED")
    if not trusted_root_file(ENGINE) or not os.access(ENGINE, os.X_OK):
        raise ValueError("TRUSTED_ENGINE_NOT_INSTALLED")
    if not trusted_root_file(APPROVAL):
        raise ValueError("LOCAL_CONSOLE_APPROVAL_MISSING")
    if APPROVAL.read_text(encoding="ascii").strip() != "LOCAL_MAC_WITH_RECOVERY":
        raise ValueError("LOCAL_CONSOLE_APPROVAL_INVALID")
    # Fail closed if there is no signed-in physical console owner.
    if os.stat("/dev/console").st_uid <= 0:
        raise ValueError("NO_LOCAL_CONSOLE_OWNER")
    # Not proof that networking is recoverable. Administrator must install
    # only with working physical console or equivalent out-of-band access.


class Session:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
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
                self.config = None
                self.owner = None
                self.started = None

    def status(self) -> dict:
        with self.lock:
            if self.process is not None:
                if self.process.poll() is not None or (
                    self.started is not None and
                    time.monotonic() - self.started > MAX_SESSION
                ) or not self.console_owner_present():
                    self.cleanup()
            return {
                "state": "engine_running_unverified" if self.process else "stopped",
                "system_vpn_verified": False,
                "owner_present": self.owner is not None,
                "maximum_session_seconds": MAX_SESSION,
            }

    def start(self, uid: int, profile: object) -> dict:
        with self.lock:
            if self.status()["state"] != "stopped":
                raise ValueError("TUN_ALREADY_RUNNING")
            if not isinstance(profile, dict):
                raise ValueError("TUN_CONFIG_NOT_OBJECT")
            encoded = json.dumps(profile, separators=(",", ":")).encode("utf-8")
            if len(encoded) > MAX_REQUEST - 1024:
                raise ValueError("TUN_CONFIG_TOO_LARGE")
            path = TRUSTED_ROOT / ("active-" + secrets.token_hex(16) + ".json")
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(encoded)
                validate_full_tun_config(path)
                subprocess.run([str(ENGINE), "check", "-c", str(path)],
                               check=True, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=20)
                child = subprocess.Popen([str(ENGINE), "run", "-c", str(path)],
                                         stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL,
                                         start_new_session=True)
                self.process = child
                self.config = path
                self.owner = uid
                self.started = time.monotonic()
                if child.poll() is not None:
                    self.cleanup()
                    raise ValueError("TUN_ENGINE_EXITED_EARLY")
                return self.status()
            except BaseException:
                if self.process is None:
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
        "status", "start", "stop"):
        raise ValueError("TUN_REQUEST_ACTION_INVALID")
    return value


def reply(conn: socket.socket, result: dict) -> None:
    conn.sendall(json.dumps(result, separators=(",", ":")).encode("utf-8") + b"\n")


def handle(conn: socket.socket, session: Session) -> None:
    conn.settimeout(5)
    try:
        if not authorized_peer(conn):
            raise ValueError("TUN_CONSOLE_OWNER_REQUIRED")
        uid, _ = conn.getpeereid()
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
