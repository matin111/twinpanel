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
import os
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


def save_state(item: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    tmp = state_path().with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(item, handle)
        handle.write("\n")
    os.replace(tmp, state_path())


def start(protocol: str, config: Path) -> dict:
    if protocol not in PROTOCOLS:
        fail("UNKNOWN_PROTOCOL")
    exe = binary_for(protocol)
    if not exe:
        fail("ENGINE_NOT_INSTALLED_OR_UNSUPPORTED")
    existing = read_state()
    if existing and process_matches(existing):
        fail("OTHER_ENGINE_ALREADY_RUNNING")
    config = config.expanduser().resolve(strict=True)
    port = validate(protocol, config)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    logpath = STATE / "engine.log"
    logfd = os.open(logpath, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    args = ([str(exe), "run", "-config", str(config)] if protocol == "v2ray"
            else [str(exe), "run", "-c", str(config)])
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
                  "mode": "local_proxy_only", "config": str(config),
                  "executable": str(exe)}
        save_state(record)
        return {"state": "process_running_unverified", "protocol": protocol,
                "pid": proc.pid, "proxy": f"127.0.0.1:{port}",
                "note": "Test with curl --socks5-hostname; no full-tunnel or remote handshake is implied"}
    except Exception:
        if "proc" in locals() and proc.poll() is None:
            proc.terminate()
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
    for needle, code in (
        ("address already in use", "PROXY_LOCAL_PORT_OCCUPIED"),
        ("permission denied", "ENGINE_PERMISSION_DENIED"),
        ("unknown outbound type", "ENGINE_UNSUPPORTED_OUTBOUND"),
        ("unknown field", "ENGINE_CONFIG_UNSUPPORTED_FIELD"),
        ("invalid config", "ENGINE_CONFIG_INVALID"),
        ("timeout", "ENGINE_REMOTE_TIMEOUT"),
        ("certificate", "ENGINE_REMOTE_TLS_CERTIFICATE_FAILURE"),
        ("quic", "ENGINE_QUIC_TRANSPORT_FAILURE"),
        ("handshake", "ENGINE_REMOTE_HANDSHAKE_FAILURE"),
        ("network is unreachable", "ENGINE_REMOTE_NETWORK_UNREACHABLE"),
        ("no such host", "ENGINE_REMOTE_DNS_FAILURE"),
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
    item = read_state()
    if item and process_matches(item):
        os.kill(item["pid"], signal.SIGTERM)
    state_path().unlink(missing_ok=True)
    return {"state": "stop_requested" if item else "stopped"}


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
    sub.add_parser("diagnose")
    sub.add_parser("stop")
    check = sub.add_parser("probe")
    check.add_argument("--expected-ip", default=None)
    run = sub.add_parser("start")
    run.add_argument("protocol", choices=PROTOCOLS)
    run.add_argument("config", type=Path)
    args = parser.parse_args()
    try:
        result = (list_protocols() if args.action == "list" else
                  status() if args.action == "status" else
                  {"state": "diagnosis", "reason": engine_failure_category()} if args.action == "diagnose" else
                  stop() if args.action == "stop" else
                  probe(args.expected_ip) if args.action == "probe" else
                  start(args.protocol, args.config))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"state": "error", "reason": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
