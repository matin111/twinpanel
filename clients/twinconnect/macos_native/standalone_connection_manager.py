#!/usr/bin/env python3
"""TwinConnect macOS unsigned *local-proxy* process manager.

No Apple Network Extension, root permission, default route, DNS rewrite or
system-wide VPN is used here. Only loopback SOCKS/HTTP proxy profiles are
allowed. This is an executable test backend, not a full-tunnel implementation.
"""
from __future__ import annotations

import argparse
import json
import ipaddress
import http.client
import os
import secrets
import socket
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home() / "Library/Application Support/TwinConnect/standalone"
PROTOCOLS = (
    "openvpn", "openconnect", "l2tp", "wireguard", "amneziawg",
    "v2ray", "hysteria2", "tuic", "anytls", "naive", "shadowtls",
    "snell", "socks5", "mieru", "trusttunnel",
)
# Separate engines can be integrated later; never claim they are implemented.
SINGBOX = {"hysteria2", "tuic", "anytls", "naive", "shadowtls", "snell", "socks5"}
EXECUTABLE = {**{p: "sing-box" for p in SINGBOX}, "v2ray": "xray"}
ARCH = "amd64" if os.uname().machine == "x86_64" else "arm64"


def binary_for(protocol: str) -> Path | None:
    if protocol == "v2ray":
        path = ROOT / "macos_native/build/xray" / ARCH / "xray"
    elif protocol in SINGBOX:
        path = ROOT / "macos_native/build/singbox" / ARCH / "sing-box"
    else:
        return None
    return path if path.is_file() and os.access(path, os.X_OK) else None


def fail(reason: str) -> None:
    raise ValueError(reason)


def validate(protocol: str, filename: Path) -> int:
    if not filename.is_file() or filename.is_symlink():
        fail("CONFIG_NOT_REGULAR_FILE")
    if filename.stat().st_size > 262144:
        fail("CONFIG_TOO_LARGE")
    try:
        obj = json.loads(filename.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        fail("CONFIG_INVALID_JSON")
    if not isinstance(obj, dict):
        fail("CONFIG_INVALID_OBJECT")
    inbounds = obj.get("inbounds")
    if not isinstance(inbounds, list) or len(inbounds) != 1:
        fail("ONE_LOCAL_PROXY_INBOUND_REQUIRED")
    inbound = inbounds[0]
    if not isinstance(inbound, dict):
        fail("INVALID_INBOUND")
    listen = inbound.get("listen", "127.0.0.1")
    if listen not in ("127.0.0.1", "::1", "localhost"):
        fail("NON_LOOPBACK_LISTENER_FORBIDDEN")
    port = inbound.get("listen_port" if protocol != "v2ray" else "port")
    if type(port) is not int or not 1024 <= port <= 65535:
        fail("INVALID_LOCAL_PROXY_PORT")
    allowed = ("socks", "http") if protocol == "v2ray" else ("socks", "http", "mixed")
    kind = inbound.get("protocol" if protocol == "v2ray" else "type")
    if kind not in allowed:
        fail("TUN_OR_NON_PROXY_INBOUND_FORBIDDEN")
    outbounds = obj.get("outbounds")
    if not isinstance(outbounds, list) or not outbounds:
        fail("OUTBOUNDS_REQUIRED")
    if protocol == "v2ray":
        if not any(isinstance(o, dict) and o.get("protocol") in ("vless", "vmess", "trojan", "shadowsocks") for o in outbounds):
            fail("XRAY_PROXY_OUTBOUND_MISSING")
    else:
        types = {o.get("type") for o in outbounds if isinstance(o, dict)}
        expected = {"socks5": "socks", "shadowtls": "shadowtls"}.get(protocol, protocol)
        if expected not in types:
            fail("PROTOCOL_OUTBOUND_MISSING")
    # Do not allow a TUN inbound anywhere in the supplied profile.
    if any(isinstance(i, dict) and i.get("type") == "tun" for i in inbounds):
        fail("TUN_INBOUND_FORBIDDEN")
    return port


def state_path() -> Path:
    return STATE / "current.json"


def measured_runtime_config(protocol: str, source: Path) -> tuple[Path, int | None, str | None]:
    """Prepare a private authenticated loopback counter without editing source."""
    if protocol != "hysteria2":
        return source, None, None
    config = json.loads(source.read_text(encoding="utf-8"))
    if "experimental" in config:
        fail("EXPERIMENTAL_CONFIG_NOT_ALLOWED")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        metrics_port = int(listener.getsockname()[1])
    secret = secrets.token_urlsafe(36)
    config["experimental"] = {"clash_api": {
        "external_controller": f"127.0.0.1:{metrics_port}",
        "secret": secret,
        "access_control_allow_origin": ["http://localhost.invalid"],
        "access_control_allow_private_network": False,
    }}
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    runtime = STATE / ("managed-" + secrets.token_hex(16) + ".json")
    fd = os.open(runtime, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config, stream)
    except Exception:
        runtime.unlink(missing_ok=True)
        raise
    return runtime, metrics_port, secret


def cleanup_runtime_config(item: dict) -> None:
    value = item.get("managed_profile")
    if not isinstance(value, str):
        return
    path = Path(value)
    if path.parent == STATE and path.name.startswith("managed-") and path.suffix == ".json":
        path.unlink(missing_ok=True)


def traffic() -> dict:
    """Real bytes transferred through this managed engine, not Mac NIC bytes."""
    item = read_state()
    if not item or not process_matches(item):
        fail("ENGINE_NOT_RUNNING")
    port, secret = item.get("metrics_port"), item.get("metrics_secret")
    if type(port) is not int or not 1024 <= port <= 65535 or \
            not isinstance(secret, str) or len(secret) < 32:
        fail("TRAFFIC_MONITOR_NOT_CONFIGURED")
    client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        client.request("GET", "/connections", headers={
            "Authorization": "Bearer " + secret,
            "Accept": "application/json",
        })
        response = client.getresponse()
        if response.status != 200:
            fail("TRAFFIC_MONITOR_UNAVAILABLE")
        raw = response.read(131073)
        if len(raw) > 131072:
            fail("TRAFFIC_RESPONSE_TOO_LARGE")
        value = json.loads(raw)
        upload, download = value.get("uploadTotal"), value.get("downloadTotal")
        if not all(type(n) is int and 0 <= n < 2**62 for n in [upload, download]):
            fail("TRAFFIC_COUNTERS_INVALID")
        return {"state": "measured", "mode": "local_proxy_only",
                "download_bytes": download, "upload_bytes": upload}
    except (OSError, ValueError, http.client.HTTPException):
        fail("TRAFFIC_MONITOR_UNAVAILABLE")
    finally:
        client.close()


def read_state() -> dict | None:
    path = state_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        fail("STATE_CORRUPTED")


def process_matches(item: dict) -> bool:
    pid = item.get("pid")
    if type(pid) is not int or pid <= 1:
        return False
    try:
        # Prevent terminating a recycled PID. Match executable and config path.
        cmd = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "command="],
            check=False, capture_output=True, text=True, timeout=3
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool(cmd and item.get("executable") in cmd and item.get("config") in cmd)


def process_start_signature(pid: int) -> str | None:
    """Tie owner liveness to a process birth time, not just a reusable PID."""
    if type(pid) is not int or pid <= 1:
        return None
    try:
        reply = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "lstart="],
            check=False, capture_output=True, text=True, timeout=3
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = reply.stdout.strip()
    return value if reply.returncode == 0 and value else None


def watch_owner(owner_pid: int, engine_pid: int, started: str) -> dict:
    """Fail closed if the owning GUI quits/crashes, without touching the OS network."""
    for _ in range(86400):
        item = read_state()
        if not item or item.get("pid") != engine_pid:
            return {"state": "watcher_finished"}
        if item.get("owner_pid") != owner_pid or item.get("owner_started") != started:
            return {"state": "watcher_replaced"}
        if not process_matches(item):
            return {"state": "engine_not_running"}
        if process_start_signature(owner_pid) != started:
            try:
                return stop()
            except (ValueError, OSError):
                return {"state": "stop_failed_state_preserved"}
        time.sleep(1)
    return {"state": "watcher_lifetime_expired"}


def save_state(item: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    tmp = state_path().with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(item, handle)
        handle.write("\n")
    os.replace(tmp, state_path())


def start(protocol: str, config: Path, owner_pid: int | None = None) -> dict:
    if protocol not in PROTOCOLS:
        fail("UNKNOWN_PROTOCOL")
    exe = binary_for(protocol)
    if not exe:
        fail("ENGINE_NOT_INSTALLED_OR_UNSUPPORTED")
    existing = read_state()
    if existing and process_matches(existing):
        fail("OTHER_ENGINE_ALREADY_RUNNING")
    # UI probes are attached to their real macOS app process so that
    # a crash cannot leave a background SOCKS engine behind.
    owner_started = None
    if owner_pid is not None:
        owner_started = process_start_signature(owner_pid)
        if not owner_started:
            fail("PROXY_OWNER_NOT_RUNNING")
    config = config.expanduser().resolve(strict=True)
    port = validate(protocol, config)
    runtime, metrics_port, metrics_secret = measured_runtime_config(protocol, config)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    logpath = STATE / "engine.log"
    # Keep this attempt's errors separate from earlier server/protocol tests.
    # A single managed engine is allowed at a time. Never return raw logs.
    logfd = os.open(logpath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    args = ([str(exe), "run", "-config", str(runtime)] if protocol == "v2ray"
            else [str(exe), "run", "-c", str(runtime)])
    try:
        with os.fdopen(logfd, "a") as log:
            proc = subprocess.Popen(
                args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, close_fds=True
            )
        time.sleep(0.6)
        if proc.poll() is not None:
            fail("ENGINE_EXITED_EARLY_CHECK_LOCAL_LOG")
        record = {"protocol": protocol, "pid": proc.pid, "port": port,
                  "mode": "local_proxy_only", "config": str(runtime),
                  "executable": str(exe)}
        if metrics_port is not None and metrics_secret is not None:
            record.update({"metrics_port": metrics_port,
                           "metrics_secret": metrics_secret,
                           "managed_profile": str(runtime)})
        if owner_pid is not None:
            record["owner_pid"] = owner_pid
            record["owner_started"] = owner_started
        save_state(record)
        if metrics_port is not None:
            # sing-box has parsed its runtime settings. Do not retain the
            # customer's Hysteria2 credentials on disk for the session.
            # Process identity still matches executable + argv config path.
            cleanup_runtime_config(record)
        if owner_pid is not None:
            # Separate watchdog survives a GUI crash; never requires root.
            try:
                subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()),
                     "watch-owner", str(owner_pid), str(proc.pid), owner_started],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, close_fds=True,
                    start_new_session=True
                )
            except OSError:
                # Fail closed rather than launching an unwatched GUI proxy.
                stop()
                fail("PROXY_WATCHDOG_START_FAILED")
        return {"state": "process_running_unverified", "protocol": protocol,
                "pid": proc.pid, "proxy": f"127.0.0.1:{port}",
                "note": "Test with curl --socks5-hostname; no full-tunnel or remote handshake is implied"}
    except Exception:
        if "proc" in locals() and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if "proc" not in locals() or proc.poll() is not None:
            cleanup_runtime_config({"managed_profile": str(runtime)})
        raise


def status() -> dict:
    item = read_state()
    if not item:
        return {"state": "stopped"}
    return {"state": "process_running_unverified" if process_matches(item) else "not_running",
            "protocol": item.get("protocol"), "pid": item.get("pid"),
            "proxy": f"127.0.0.1:{item.get('port')}"}



def proxy_failure_category(code: int) -> str:
    """Classify curl failure without exposing a remote host or credential."""
    return {
        5: "PROXY_DNS_LOOKUP_FAILED",
        6: "REMOTE_DNS_LOOKUP_FAILED",
        7: "PROXY_TCP_UNREACHABLE",
        22: "PROXY_HTTPS_HTTP_ERROR",
        28: "PROXY_OR_REMOTE_TIMEOUT",
        35: "PROXY_TLS_HANDSHAKE_FAILED",
        52: "PROXY_EMPTY_RESPONSE",
        55: "PROXY_UPLOAD_FAILED",
        56: "PROXY_DOWNLOAD_FAILED",
        60: "PROXY_REMOTE_CERTIFICATE_INVALID",
        97: "PROXY_SOCKS_HANDSHAKE_FAILED",
    }.get(code, "PROXY_EGRESS_REQUEST_FAILED")


def engine_failure_category() -> str:
    """Report only a safe fixed category derived from local engine logs.

    Never return log lines; engines may include auth secrets, URLs or SNI.
    """
    try:
        with (STATE / "engine.log").open("rb") as stream:
            stream.seek(max(0, stream.seek(0, os.SEEK_END) - 65536))
            data = stream.read().decode("utf-8", errors="replace").lower()
    except OSError:
        return "ENGINE_LOG_UNAVAILABLE"
    # Check specific errors before generic QUIC/handshake text. Match only
    # known fixed phrases and return a fixed code, never any user data.
    for needle, code in (
        ("address already in use", "PROXY_LOCAL_PORT_OCCUPIED"),
        ("operation not permitted", "ENGINE_PERMISSION_DENIED"),
        ("permission denied", "ENGINE_PERMISSION_DENIED"),
        ("unknown outbound type", "ENGINE_UNSUPPORTED_OUTBOUND"),
        ("unknown field", "ENGINE_CONFIG_UNSUPPORTED_FIELD"),
        ("invalid config", "ENGINE_CONFIG_INVALID"),
        ("authentication failed", "HYSTERIA2_REMOTE_AUTH_REJECTED"),
        ("unauthorized", "HYSTERIA2_REMOTE_AUTH_REJECTED"),
        ("certificate is not valid for", "TLS_CERTIFICATE_HOSTNAME_MISMATCH"),
        ("cannot validate certificate for", "TLS_CERTIFICATE_HOSTNAME_MISMATCH"),
        ("certificate is valid for", "TLS_CERTIFICATE_HOSTNAME_MISMATCH"),
        ("certificate has expired", "TLS_CERTIFICATE_EXPIRED_OR_CLOCK"),
        ("certificate is not yet valid", "TLS_CERTIFICATE_EXPIRED_OR_CLOCK"),
        ("certificate is not trusted", "TLS_CERTIFICATE_UNTRUSTED_CA"),
        ("certificate signed by unknown authority", "TLS_CERTIFICATE_UNTRUSTED_CA"),
        ("unknown authority", "TLS_CERTIFICATE_UNTRUSTED_CA"),
        ("certificate verify failed", "ENGINE_REMOTE_TLS_CERTIFICATE_FAILURE"),
        ("x509:", "ENGINE_REMOTE_TLS_CERTIFICATE_FAILURE"),
        ("tls: failed", "ENGINE_REMOTE_TLS_HANDSHAKE_FAILED"),
        ("connection refused", "ENGINE_REMOTE_CONNECTION_REFUSED"),
        ("network is unreachable", "ENGINE_REMOTE_NETWORK_UNREACHABLE"),
        ("no route to host", "ENGINE_REMOTE_NETWORK_UNREACHABLE"),
        ("no such host", "ENGINE_REMOTE_DNS_FAILURE"),
        ("context deadline exceeded", "ENGINE_REMOTE_TIMEOUT"),
        ("i/o timeout", "ENGINE_REMOTE_TIMEOUT"),
        ("timeout", "ENGINE_REMOTE_TIMEOUT"),
        ("handshake failed", "ENGINE_REMOTE_HANDSHAKE_FAILURE"),
        ("quic", "ENGINE_QUIC_TRANSPORT_FAILURE"),
    ):
        if needle in data:
            return code
    return "ENGINE_FAILURE_NOT_CLASSIFIED"


def probe(expected_ip: str | None = None) -> dict:
    """Verify proxied HTTPS egress, never claim a system-wide VPN."""
    item = read_state()
    if not item or not process_matches(item):
        fail("ENGINE_NOT_RUNNING")
    if expected_ip is not None:
        try:
            expected_ip = str(ipaddress.ip_address(expected_ip))
        except ValueError:
            fail("EXPECTED_IP_INVALID")
    port = item.get("port")
    if type(port) is not int or not 1024 <= port <= 65535:
        fail("PROXY_PORT_INVALID")
    try:
        response = subprocess.run([
            "/usr/bin/curl", "-4", "--silent", "--show-error", "--fail",
            "--connect-timeout", "5", "--max-time", "15",
            "--proxy", f"socks5h://127.0.0.1:{port}",
            "--noproxy", "",
            "https://api.ipify.org"
        ], capture_output=True, text=True, timeout=18, check=False)
    except (OSError, subprocess.TimeoutExpired):
        fail("PROXY_EGRESS_REQUEST_FAILED")
    if response.returncode != 0:
        fail(proxy_failure_category(response.returncode))
    try:
        ip = ipaddress.ip_address(response.stdout.strip())
    except ValueError:
        fail("PROXY_EGRESS_INVALID_IP_RESPONSE")
    if ip.version != 4:
        fail("PROXY_EGRESS_UNEXPECTED_ADDRESS_FAMILY")
    matched = expected_ip is not None and str(ip) == expected_ip
    return {
        "state": "egress_verified" if matched else
                 "egress_ip_mismatch" if expected_ip is not None else
                 "proxy_egress_reachable",
        "protocol": item["protocol"], "egress_ip": str(ip),
        "expected_egress_ip": expected_ip,
        "verified_expected_egress": matched,
        "system_wide_vpn": False,
        "note": "Only this SOCKS proxy HTTPS request was tested; other apps and DNS are not tunneled",
    }



def stop() -> dict:
    """Stop only the exact process this manager started.

    Never remove the state record while a matching process is still live:
    that would leave an unmanaged proxy which the user cannot disconnect.
    Never touch the system proxy, default route, DNS, or unrelated processes.
    """
    item = read_state()
    if not item:
        return {"state": "stopped"}
    if not process_matches(item):
        cleanup_runtime_config(item)
        state_path().unlink(missing_ok=True)
        return {"state": "stopped", "reason": "ENGINE_NOT_RUNNING"}
    pid = item["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        cleanup_runtime_config(item)
        state_path().unlink(missing_ok=True)
        return {"state": "stopped"}
    except PermissionError:
        fail("ENGINE_STOP_PERMISSION_DENIED")
    for _ in range(30):
        if not process_matches(item):
            cleanup_runtime_config(item)
            state_path().unlink(missing_ok=True)
            return {"state": "stopped"}
        time.sleep(0.1)
    # A still-matching engine belongs to this manager. Give SIGKILL only
    # to that validated PID, never to a process group or a recycled PID.
    if process_matches(item):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError:
            fail("ENGINE_STOP_PERMISSION_DENIED")
    for _ in range(15):
        if not process_matches(item):
            cleanup_runtime_config(item)
            state_path().unlink(missing_ok=True)
            return {"state": "stopped"}
        time.sleep(0.1)
    fail("ENGINE_STILL_RUNNING_STATE_PRESERVED")


def list_protocols() -> dict:
    return {"mode": "local_proxy_only", "default_route_modified": False,
            "protocols": [
                {"code": p,
                 "backend": EXECUTABLE.get(p),
                 "state": ("proxy_engine_present" if binary_for(p) else
                           "backend_not_installed" if p in EXECUTABLE else
                           "not_integrated")}
                for p in PROTOCOLS
            ]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    sub.add_parser("status")
    sub.add_parser("traffic")
    sub.add_parser("diagnose")
    sub.add_parser("stop")
    check = sub.add_parser("probe")
    check.add_argument("--expected-ip", default=None)
    run = sub.add_parser("start")
    run.add_argument("protocol", choices=PROTOCOLS)
    run.add_argument("config", type=Path)
    run.add_argument("--owner-pid", type=int, default=None)
    watcher = sub.add_parser("watch-owner", help=argparse.SUPPRESS)
    watcher.add_argument("owner_pid", type=int)
    watcher.add_argument("engine_pid", type=int)
    watcher.add_argument("owner_started")
    args = parser.parse_args()
    try:
        result = (list_protocols() if args.action == "list" else
                  status() if args.action == "status" else
                  traffic() if args.action == "traffic" else
                  {"state": "diagnosis", "reason": engine_failure_category()} if args.action == "diagnose" else
                  stop() if args.action == "stop" else
                  probe(args.expected_ip) if args.action == "probe" else
                  watch_owner(args.owner_pid, args.engine_pid, args.owner_started)
                      if args.action == "watch-owner" else
                  start(args.protocol, args.config, args.owner_pid))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"state": "error", "reason": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
