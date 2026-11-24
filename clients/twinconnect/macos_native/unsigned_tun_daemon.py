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
import tempfile
import time
import urllib.request

from unsigned_tun_policy import (TRUSTED_ROOT, trusted_root_file,
                                 validate_full_tun_config)
from openvpn_profile_review import review as review_openvpn
from tun_vps_management_guard import guard_candidate, system_dns_resolvers
from unsigned_mieru_profile import validate_mbox_tun_config
from unsigned_trusttunnel_profile import (
    trusted_unsigned_runtime, trusttunnel_singbox_tun, SOCKS_PORT)

from unsigned_sudoku_profile import sudoku_runtime, sudoku_singbox_tun

SOCKET_PATH = Path("/var/run/twinconnect-tun.sock")
ENGINE = TRUSTED_ROOT / "sing-box"
MIERU_ENGINE = TRUSTED_ROOT / "mbox"
TRUSTTUNNEL_CLIENT = TRUSTED_ROOT / "trusttunnel_client"
SUDOKU_CLIENT = TRUSTED_ROOT / "sudoku"
APPROVAL = TRUSTED_ROOT / "local-console-approval"
WATCHDOG = TRUSTED_ROOT / "unsigned_tun_watchdog.py"
OPENVPN = TRUSTED_ROOT / "openvpn/bin/openvpn"
OPENVPN_REVIEW = TRUSTED_ROOT / "openvpn_profile_review.py"
MAX_REQUEST = 262144
MAX_SESSION = 600
VPS_SESSION = 45
# A distinct root-owned approval mode for the owner-authorized remote VPS.
# Retain a watchdog deadline; do not create an unlimited unattended tunnel.
VPS_EXTENDED_SESSION = 30 * 24 * 60 * 60
VPS_EXTENDED_APPROVAL = "VPS_OOB_CONSOLE_LONG_SESSION_30_DAYS"
VPS_TRIAL_APPROVAL = "VPS_OOB_CONSOLE_45_SECONDS"


def approval_mode() -> str:
    try:
        return APPROVAL.read_text(encoding="ascii").strip()
    except OSError:
        return ""


def vps_mode() -> bool:
    # Both VPS approval modes MUST keep the Termalin management peer outside
    # the TUN route, even when the user accepts temporary network disruption.
    return approval_mode() in (VPS_TRIAL_APPROVAL, VPS_EXTENDED_APPROVAL)


def session_limit() -> int:
    """The chosen root-owned approval controls the independent watchdog TTL."""
    mode = approval_mode()
    if mode == VPS_TRIAL_APPROVAL:
        return VPS_SESSION
    if mode == VPS_EXTENDED_APPROVAL:
        return VPS_EXTENDED_SESSION
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
    if approval not in ("LOCAL_MAC_WITH_RECOVERY", VPS_TRIAL_APPROVAL,
                        VPS_EXTENDED_APPROVAL):
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
    """Verify actual HTTPS exit through macOS' observed utun route.

    First try DNS+HTTPS. A second, certificate-verified numeric HTTPS target
    permits genuine proof even when the physical DNS resolver is briefly
    unavailable while the system route is coming up. Both destinations
    MUST route via utun. We never accept an unverified status as Connected.
    No proxy env, insecure TLS, user-defined endpoint or direct fallback.
    """
    if observe_route().get("route_state") != "utun_route_observed_unverified":
        return {"https_state": "tun_route_not_observed"}
    import ipaddress

    def verified_trace(url: str, timeout: float) -> str | None:
        request = urllib.request.Request(
            url, headers={"User-Agent": "TwinConnect-TUN-Health/1.0"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as reply:
            if reply.status != 200:
                return None
            raw = reply.read(4097)
        if len(raw) > 4096:
            return None
        rows = {}
        for line in raw.decode("utf-8", errors="strict").splitlines():
            key, sep, value = line.partition("=")
            if sep and key in ("ip", "warp", "loc"):
                rows[key] = value
        ip = rows.get("ip", "")
        if not ip or not ipaddress.ip_address(ip).is_global:
            return None
        return ip

    # The local socket's probe timeout is six seconds. Bound both HTTPS
    # attempts below that, including a small margin for IPC overhead.
    for url, timeout in (
        ("https://www.cloudflare.com/cdn-cgi/trace", 2.7),
        ("https://1.1.1.1/cdn-cgi/trace", 2.0),
    ):
        # Do not promote an interface-only route. Re-confirm the kernel
        # route immediately before each authenticated HTTPS probe.
        if observe_route().get("route_state") != "utun_route_observed_unverified":
            return {"https_state": "tun_route_not_observed"}
        try:
            ip = verified_trace(url, timeout)
            if ip:
                return {"https_state": "system_https_reachable",
                        "observed_exit_ip": ip,
                        "system_vpn_verified": False}
        except (OSError, ValueError, UnicodeError, TimeoutError):
            continue
    return {"https_state": "unreachable"}


def classify_engine_stderr(raw: bytes) -> str:
    """Return only fixed reason codes; NEVER echo raw sing-box output."""
    # Error streams can include private endpoints or profile values.
    # Inspect in memory, keep only a category and discard the original.
    message = raw[:16384].decode("utf-8", errors="replace").lower()
    if "operation not permitted" in message or "permission denied" in message:
        return "TUN_ENGINE_PERMISSION_DENIED"
    if ("no such device" in message or "device not configured" in message
            or "create tun" in message or "configure tun" in message
            or "utun" in message):
        return "TUN_ENGINE_INTERFACE_FAILED"
    if "address already in use" in message or "file exists" in message:
        return "TUN_ENGINE_CONFLICT"
    if "route" in message and ("failed" in message or "error" in message):
        return "TUN_ENGINE_ROUTE_ERROR"
    if "network is unreachable" in message or "no route to host" in message:
        return "TUN_ENGINE_NETWORK_UNREACHABLE"
    if ("invalid" in message or "unsupported" in message or
            "unknown field" in message):
        return "TUN_ENGINE_RUNTIME_CONFIG_INVALID"
    return "TUN_ENGINE_EXITED_BEFORE_ROUTE"


def trusttunnel_verified_socks_exit(pid: int, port: int = SOCKS_PORT) -> str:
    """Fail closed until HTTPS proves the official SOCKS endpoint is usable.

    A local LISTEN socket is NOT evidence of an authenticated VPN session.
    Curl verifies the public TLS target certificate; no insecure flag,
    proxy env, secret arguments, arbitrary URLs, or local direct fallback.
    """
    import ipaddress
    # The official CLI may listen before the upstream HTTP/2 connection
    # authenticates. Retry bounded SOCKS HTTPS; never promote LISTEN alone.
    deadline = time.monotonic() + 25.0
    for _ in range(20):
        if time.monotonic() >= deadline:
            break
        try:
            if os.getpgid(pid) != pid:
                raise ValueError("TRUSTTUNNEL_CLIENT_EXITED")
        except ProcessLookupError:
            raise ValueError("TRUSTTUNNEL_CLIENT_EXITED") from None
        # Only accept a proxy listener owned by the root-started transport,
        # never a random existing unprivileged process bound to loopback.
        try:
            port_owner = subprocess.run(
                ["/usr/sbin/lsof", "-nP", "-a", "-p", str(pid),
                 f"-iTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True, timeout=3, check=False)
        except (OSError, subprocess.TimeoutExpired):
            port_owner = None
        if port_owner is not None and port_owner.returncode == 0:
            try:
                trace = subprocess.run(
                    ["/usr/bin/curl", "--silent", "--show-error", "--fail",
                     "--max-time", "4", "--connect-timeout", "2",
                     "--socks5-hostname", f"127.0.0.1:{port}",
                     "https://1.1.1.1/cdn-cgi/trace"],
                    capture_output=True, timeout=7, check=False)
                if trace.returncode == 0 and len(trace.stdout) <= 8192:
                    for line in trace.stdout.decode(
                            "utf-8", errors="strict").splitlines():
                        if line.startswith("ip="):
                            address = ipaddress.ip_address(line[3:])
                            if address.is_global:
                                return str(address)
            except (OSError, ValueError, UnicodeError,
                    subprocess.TimeoutExpired):
                pass
        time.sleep(0.35)
    raise ValueError("TRUSTTUNNEL_SOCKS_HTTPS_NOT_VERIFIED")


class Session:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.watchdog: subprocess.Popen | None = None
        self.config: Path | None = None
        self.owner: int | None = None
        self.started: float | None = None
        self.engine_stderr = None
        self.transport_process: subprocess.Popen | None = None
        self.transport_config: Path | None = None
        self.transport_stderr = None
        self.transport_protocol = "trusttunnel"

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
                transport = self.transport_process
                if transport is not None and transport.poll() is None:
                    try:
                        os.killpg(transport.pid, signal.SIGTERM)
                        transport.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(transport.pid, signal.SIGKILL)
                        transport.wait(timeout=5)
                    except ProcessLookupError:
                        pass
                if self.transport_config is not None:
                    self.transport_config.unlink(missing_ok=True)
                self.transport_process = None
                self.transport_config = None
                if self.transport_stderr is not None:
                    self.transport_stderr.close()
                    self.transport_stderr = None
                self.process = None
                self.watchdog = None
                self.config = None
                self.owner = None
                self.started = None
                if self.engine_stderr is not None:
                    self.engine_stderr.close()
                    self.engine_stderr = None

    def status(self) -> dict:
        with self.lock:
            if self.process is not None:
                if (self.transport_process is not None and
                        self.transport_process.poll() is not None) or (
                    self.process.poll() is not None
                ) or (
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
                # Only the root daemon knows whether this sing-box SOCKS
                # outbound belongs to the separately supervised official
                # TrustTunnel client. Never mislabel it as generic SOCKS5.
                if (self.transport_process is not None and
                        self.transport_process.poll() is None and
                        self.owner is not None):
                    status["protocol_code"] = self.transport_protocol
            return status

    def start(self, uid: int, profile: object) -> dict:
        with self.lock:
            if self.status()["state"] != "stopped":
                raise ValueError("TUN_ALREADY_RUNNING")
            if not isinstance(profile, dict):
                raise ValueError("TUN_CONFIG_NOT_OBJECT")
            if os.path.lexists("/private/var/run/twinconnect-killswitch-control/lease.json"):
                raise ValueError("TUN_KS_RECONNECT_NOT_AUTHORIZED")
            use_trusttunnel = profile.get("mode") == "trusttunnel"
            use_sudoku = profile.get("mode") == "sudoku"
            trust_toml = ""
            sudoku_json = ""
            pinned_trust_endpoint_ips: tuple[str, ...] = ()
            if use_trusttunnel:
                if (set(profile) != {"mode", "deeplink"} or
                        not isinstance(profile["deeplink"], str) or
                        len(profile["deeplink"]) > 16384):
                    raise ValueError("TRUSTTUNNEL_REQUEST_INVALID")
                if (not trusted_root_file(TRUSTTUNNEL_CLIENT) or
                        not os.access(TRUSTTUNNEL_CLIENT, os.X_OK)):
                    raise ValueError("TRUSTTUNNEL_ROOT_CLIENT_NOT_INSTALLED")
                trust_toml, pinned_trust_endpoint_ips = (
                    trusted_unsigned_runtime(profile["deeplink"]))
                # The supplied link is never an arbitrary sing-box profile.
                profile = trusttunnel_singbox_tun()
            if use_sudoku:
                if set(profile) != {"mode", "profile"}:
                    raise ValueError("SUDOKU_REQUEST_INVALID")
                if not trusted_root_file(SUDOKU_CLIENT) or not os.access(SUDOKU_CLIENT, os.X_OK):
                    raise ValueError("SUDOKU_ROOT_CLIENT_NOT_INSTALLED")
                sudoku_json, pinned_trust_endpoint_ips = sudoku_runtime(profile["profile"])
                profile = sudoku_singbox_tun()
            use_openvpn = profile.get("mode") == "openvpn"
            # Only a single, tightly-reviewed Mieru outbound can select the
            # separately staged mbox build. All existing VPNs keep sing-box.
            outbounds = profile.get("outbounds")
            use_mieru = (not use_openvpn and
                         isinstance(outbounds, list) and len(outbounds) == 1 and
                         isinstance(outbounds[0], dict) and
                         outbounds[0].get("type") == "mieru")
            if use_mieru:
                validate_mbox_tun_config(profile)
                if (not trusted_root_file(MIERU_ENGINE) or
                        not os.access(MIERU_ENGINE, os.X_OK)):
                    raise ValueError("MIERU_ROOT_ENGINE_NOT_INSTALLED")
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
                engine = MIERU_ENGINE if use_mieru else ENGINE
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
                if use_sudoku:
                    sdk_path = path.with_suffix(".sudoku.json")
                    sdk_fd = os.open(sdk_path, os.O_CREAT | os.O_EXCL |
                                     os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                    self.transport_config = sdk_path
                    with os.fdopen(sdk_fd, "w", encoding="utf-8") as sdk_file:
                        sdk_file.write(sudoku_json)
                    self.transport_stderr = tempfile.TemporaryFile(mode="w+b")
                    try:
                        subprocess.run([str(SUDOKU_CLIENT), "-c", str(sdk_path), "-test"],
                                       check=True, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=15)
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                        raise ValueError("SUDOKU_CORE_CONFIG_REJECTED") from None
                    self.transport_process = subprocess.Popen(
                        [str(SUDOKU_CLIENT), "-c", str(sdk_path)],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=self.transport_stderr, start_new_session=True)
                    self.transport_protocol = "sudoku"
                    try:
                        trusttunnel_verified_socks_exit(self.transport_process.pid)
                    except ValueError:
                        raise ValueError("SUDOKU_SOCKS_HTTPS_NOT_VERIFIED") from None
                if use_trusttunnel:
                    self.transport_protocol = "trusttunnel"
                    # Keep private username/password and pinned TLS cert in
                    # ROOT-owned 0600 TOML; never argv, logs or process env.
                    tt_path = path.with_suffix(".tt.toml")
                    tt_fd = os.open(tt_path, os.O_CREAT | os.O_EXCL |
                                    os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                    self.transport_config = tt_path
                    with os.fdopen(tt_fd, "w", encoding="utf-8") as tt_file:
                        tt_file.write(trust_toml)
                    self.transport_stderr = tempfile.TemporaryFile(mode="w+b")
                    transport = subprocess.Popen(
                        [str(TRUSTTUNNEL_CLIENT), "--config", str(tt_path),
                         "--loglevel", "error"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=self.transport_stderr,
                        start_new_session=True)
                    self.transport_process = transport
                    # The initial SOCKS listener appears before the HTTPS
                    # session is authenticated. Never start system TUN on
                    # this listener alone: require a verified remote exit.
                    trusttunnel_verified_socks_exit(transport.pid)
                if use_openvpn:
                    command = [str(engine), "--config", str(path),
                               "--script-security", "1", "--auth-nocache",
                               # Server-pushed routes and DNS are prohibited
                               # until physical-console recovery and an
                               # independently reviewed route policy exist.
                               "--route-nopull"]
                else:
                    validate_full_tun_config(path)
                    if vps_mode():
                        # Preserve the independent Termalin control transport
                        # outside sing-box routing in BOTH VPS modes.
                        # Fail closed if there is no validated active peer.
                        profile = guard_candidate(
                            profile,
                            dns_servers=system_dns_resolvers()
                            if approval_mode() == VPS_EXTENDED_APPROVAL else (),
                            endpoint_ips=pinned_trust_endpoint_ips)
                        path.write_text(json.dumps(profile, separators=(",", ":")),
                                        encoding="utf-8")
                        validate_full_tun_config(path)
                    elif use_trusttunnel or use_sudoku:
                        # Console-local mode still needs the root-pinned
                        # upstream to bypass the system-wide TUN itself.
                        profile = guard_candidate(
                            profile, peers=pinned_trust_endpoint_ips)
                        path.write_text(json.dumps(profile, separators=(",", ":")),
                                        encoding="utf-8")
                        validate_full_tun_config(path)
                    try:
                        subprocess.run([str(engine), "check", "-c", str(path)],
                                       check=True, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=20)
                    except subprocess.CalledProcessError:
                        # Never echo sing-box output: it may contain secrets.
                        raise ValueError("SINGBOX_CONFIG_REJECTED") from None
                    except subprocess.TimeoutExpired:
                        raise ValueError("SINGBOX_CONFIG_CHECK_TIMEOUT") from None
                    command = [str(engine), "run", "-c", str(path)]
                # The runtime error stream stays in an anonymous tempfile:
                # never write sensitive sing-box errors to logs or disk paths.
                self.engine_stderr = tempfile.TemporaryFile(mode="w+b")
                child = subprocess.Popen(command,
                                         stdin=subprocess.DEVNULL,
                                         stdout=subprocess.DEVNULL,
                                         stderr=self.engine_stderr,
                                         start_new_session=True)
                self.process = child
                self.config = path
                self.owner = uid
                self.started = time.monotonic()
                # Engine must never run without independent daemon-death
                # supervision. Wait for the watchdog to install its Darwin
                # NOTE_EXIT kqueue filter before replying success.
                watcher_args = [
                    sys.executable, str(WATCHDOG), "--parent",
                    str(os.getpid()), "--engine", str(child.pid),
                    "--seconds", str(session_limit())]
                if (use_trusttunnel or use_sudoku) and self.transport_process is not None:
                    watcher_args.extend([
                        "--secondary-engine",
                        str(self.transport_process.pid)])
                watcher = subprocess.Popen(
                    watcher_args,
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
                for _ in range(32):
                    if child.poll() is not None:
                        error_code = "TUN_ENGINE_EXITED_BEFORE_ROUTE"
                        if self.engine_stderr is not None:
                            self.engine_stderr.flush()
                            self.engine_stderr.seek(0)
                            error_code = classify_engine_stderr(
                                self.engine_stderr.read(16384))
                        raise ValueError(error_code)
                    if watcher.poll() is not None:
                        raise ValueError("TUN_WATCHDOG_EXITED_BEFORE_ROUTE")
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
            UnicodeError, json.JSONDecodeError) as error:
        # The daemon never echoes secrets or arbitrary error messages.
        # Only fixed uppercase machine codes are eligible for client display.
        detail = str(error)
        safe = (detail if isinstance(error, ValueError) and
                3 <= len(detail) <= 64 and
                detail.replace("_", "").isalnum() and
                detail == detail.upper() else "TUN_RUNTIME_REJECTED")
        try:
            reply(conn, {"state": "rejected", "system_vpn_verified": False,
                         "reason": safe})
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
