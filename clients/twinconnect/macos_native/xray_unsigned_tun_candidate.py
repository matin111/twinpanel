#!/usr/bin/env python3
"""Prepare an OFFLINE sing-box TUN candidate from one Xray VLESS outbound.

Does not start an engine, touch routes, persist secrets, or claim VPN connectivity.
Only explicitly reviewed TCP/TLS, TCP/REALITY or WS/TLS streams are supported.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from unsigned_tun_policy import validate_full_tun_config

MAX_CONFIG = 262144


def convert(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("XRAY_CONFIG_NOT_OBJECT")
    outbounds = data.get("outbounds")
    if not isinstance(outbounds, list):
        raise ValueError("XRAY_OUTBOUNDS_REQUIRED")
    remote = [o for o in outbounds if isinstance(o, dict) and o.get("protocol") == "vless"]
    if len(remote) != 1:
        raise ValueError("SINGLE_VLESS_OUTBOUND_REQUIRED")
    outbound = remote[0]
    settings = outbound.get("settings")
    if not isinstance(settings, dict) or set(settings) != {"vnext"}:
        raise ValueError("XRAY_VLESS_SETTINGS_UNSUPPORTED")
    nodes = settings["vnext"]
    if not isinstance(nodes, list) or len(nodes) != 1 or not isinstance(nodes[0], dict):
        raise ValueError("SINGLE_VLESS_SERVER_REQUIRED")
    node = nodes[0]
    if set(node) != {"address", "port", "users"}:
        raise ValueError("VLESS_SERVER_FIELDS_UNSUPPORTED")
    if not isinstance(node["address"], str) or not node["address"] or any(c.isspace() for c in node["address"]):
        raise ValueError("VLESS_SERVER_INVALID")
    if type(node["port"]) is not int or not 1 <= node["port"] <= 65535:
        raise ValueError("VLESS_PORT_INVALID")
    users = node["users"]
    if not isinstance(users, list) or len(users) != 1 or not isinstance(users[0], dict):
        raise ValueError("SINGLE_VLESS_USER_REQUIRED")
    user = users[0]
    if not isinstance(user.get("id"), str) or not user["id"]:
        raise ValueError("VLESS_USER_INVALID")
    if user.get("encryption", "none") != "none":
        raise ValueError("VLESS_ENCRYPTION_UNSUPPORTED")
    if set(user) - {"id", "encryption", "flow", "level", "email"}:
        raise ValueError("VLESS_USER_FIELDS_UNSUPPORTED")
    stream = outbound.get("streamSettings")
    if not isinstance(stream, dict):
        raise ValueError("VLESS_TRANSPORT_UNSUPPORTED")
    transport = stream.get("network", "tcp")
    if transport not in ("tcp", "ws"):
        raise ValueError("VLESS_TRANSPORT_UNSUPPORTED")
    sec = stream.get("security")
    if sec not in ("tls", "reality") or (transport == "ws" and sec != "tls"):
        raise ValueError("VLESS_SECURE_TRANSPORT_REQUIRED")
    sec_key = "tlsSettings" if sec == "tls" else "realitySettings"
    allowed = {"network", "security", sec_key}
    if transport == "ws":
        allowed.add("wsSettings")
    if set(stream) - allowed:
        raise ValueError("VLESS_STREAM_FIELDS_UNSUPPORTED")
    opts = stream.get(sec_key)
    if not isinstance(opts, dict):
        raise ValueError("VLESS_SECURITY_SETTINGS_REQUIRED")
    sni = opts.get("serverName")
    if not isinstance(sni, str) or not sni:
        raise ValueError("VLESS_SNI_REQUIRED")
    tls = {"enabled": True, "server_name": sni}
    if sec == "tls":
        if set(opts) - {"serverName", "allowInsecure", "alpn", "fingerprint"}:
            raise ValueError("VLESS_TLS_FIELDS_UNSUPPORTED")
        if opts.get("allowInsecure") is True:
            raise ValueError("INSECURE_TLS_FORBIDDEN")
        if opts.get("alpn"):
            tls["alpn"] = opts["alpn"]
    else:
        if set(opts) - {"serverName", "publicKey", "shortId", "fingerprint", "spiderX"}:
            raise ValueError("VLESS_REALITY_FIELDS_UNSUPPORTED")
        if not isinstance(opts.get("publicKey"), str) or not opts["publicKey"]:
            raise ValueError("VLESS_REALITY_KEY_REQUIRED")
        tls["reality"] = {"enabled": True, "public_key": opts["publicKey"],
                          "short_id": opts.get("shortId", "")}
    if opts.get("fingerprint"):
        tls["utls"] = {"enabled": True, "fingerprint": opts["fingerprint"]}
    proxy = {"type": "vless", "tag": "proxy", "server": node["address"],
             "server_port": node["port"], "uuid": user["id"], "tls": tls}
    if transport == "ws":
        if user.get("flow"):
            raise ValueError("VLESS_WS_FLOW_UNSUPPORTED")
        ws = stream.get("wsSettings")
        if not isinstance(ws, dict) or set(ws) - {"path", "headers"}:
            raise ValueError("VLESS_WS_SETTINGS_UNSUPPORTED")
        path = ws.get("path")
        if (not isinstance(path, str) or not path.startswith("/")
                or len(path.encode("utf-8")) > 1024
                or "\r" in path or "\n" in path):
            raise ValueError("VLESS_WS_PATH_INVALID")
        transport_out = {"type": "ws", "path": path}
        headers = ws.get("headers", {})
        if not isinstance(headers, dict) or set(headers) - {"Host"}:
            raise ValueError("VLESS_WS_HEADERS_UNSUPPORTED")
        if "Host" in headers:
            host = headers["Host"]
            if (not isinstance(host, str) or not host
                    or len(host.encode("utf-8")) > 255
                    or any(c in host for c in ("\r", "\n", "/", " "))):
                raise ValueError("VLESS_WS_HOST_INVALID")
            transport_out["headers"] = {"Host": host}
        proxy["transport"] = transport_out
    if user.get("flow"):
        if user["flow"] != "xtls-rprx-vision":
            raise ValueError("VLESS_FLOW_UNSUPPORTED")
        proxy["flow"] = user["flow"]
    candidate = {
        "log": {"level": "error"},
        "inbounds": [{"type": "tun", "tag": "twinconnect-tun",
                      "address": ["172.19.0.1/30"],
                      "auto_route": True, "auto_redirect": False,
                      "strict_route": False, "stack": "system"}],
        "outbounds": [proxy],
        "route": {"final": "proxy", "auto_detect_interface": True},
    }
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--stdin", action="store_true", help="Read profile from stdin; emit TUN JSON on stdout")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--engine", type=Path, help="Optional sing-box binary for offline 'check'")
    args = parser.parse_args()
    try:
        if args.stdin == (args.source is not None) or (args.stdin == (args.output is not None)):
            raise ValueError("INPUT_OUTPUT_MODE_INVALID")
        if args.stdin:
            raw = sys.stdin.buffer.read(MAX_CONFIG + 1)
            if not raw or len(raw) > MAX_CONFIG:
                raise ValueError("XRAY_SOURCE_UNTRUSTED")
            candidate = convert(json.loads(raw))
        else:
            source = args.source
            if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_CONFIG:
                raise ValueError("XRAY_SOURCE_UNTRUSTED")
            if args.output.exists() or args.output.is_symlink() or not args.output.parent.is_dir():
                raise ValueError("OUTPUT_UNSAFE")
            candidate = convert(json.loads(source.read_text(encoding="utf-8")))
        encoded = json.dumps(candidate, separators=(",", ":")).encode()
        import tempfile
        with tempfile.TemporaryDirectory(prefix="twinconnect-tun-review-") as folder:
            candidate_file = Path(folder) / "candidate.json"
            fd = os.open(candidate_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(encoded)
            validate_full_tun_config(candidate_file)
            if args.engine:
                import subprocess
                result = subprocess.run([str(args.engine), "check", "-c", str(candidate_file)],
                                        capture_output=True, timeout=20)
                if result.returncode:
                    raise ValueError("SINGBOX_CONFIGURATION_REJECTED")
        if args.stdin:
            sys.stdout.buffer.write(encoded + b"\n")
        else:
            fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(encoded)
            print("VLESS_TUN_CANDIDATE_VALIDATED_OFFLINE; NOT_CONNECTED; NO_ROUTES_CHANGED")
        return 0
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(str(exc) if str(exc).isupper() and len(str(exc)) < 90 else
              "VLESS_TUN_CANDIDATE_FAILED", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())