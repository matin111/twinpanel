#!/usr/bin/env python3
"""Unprivileged TwinConnect AppKit client for local root TUN service.

No sudo, shell, routes, DNS changes or secret-bearing argv. On a normal
cloud Mac this fails closed because the local-console daemon is not installed.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import socket
import sys
from pathlib import Path

SOCKET = Path("/var/run/twinconnect-tun.sock")
MAX_BYTES = 262144


def encode_request(action: str, config: object = None) -> bytes:
    if action not in ("status", "start", "stop"):
        raise ValueError("INVALID_ACTION")
    request: dict = {"action": action}
    if action == "start":
        if not isinstance(config, dict):
            raise ValueError("INVALID_TUN_PROFILE")
        request["config"] = config
    data = (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("PROFILE_TOO_LARGE")
    return data


def query(action: str, config: object = None,
          socket_path: Path = SOCKET) -> dict:
    try:
        info = socket_path.lstat()
    except OSError:
        raise ValueError("TUN_SERVICE_UNAVAILABLE") from None
    # Never send VPN credentials to a user's fake socket. The trusted local
    # service binds /var/run with root ownership and validates peer UID.
    if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0 or
            info.st_mode & 0o022):
        raise ValueError("TUN_SERVICE_UNTRUSTED")
    data = encode_request(action, config)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(6)
        client.connect(str(socket_path))
        client.sendall(data)
        answer = bytearray()
        while len(answer) < 4096:
            chunk = client.recv(min(1024, 4096 - len(answer)))
            if not chunk:
                break
            answer.extend(chunk)
            if b"\n" in chunk:
                break
    if b"\n" not in answer:
        raise ValueError("TUN_SERVICE_RESPONSE_INVALID")
    result = json.loads(answer.split(b"\n", 1)[0])
    if not isinstance(result, dict) or result.get("state") not in (
            "engine_running_unverified", "stopped", "rejected"):
        raise ValueError("TUN_SERVICE_RESPONSE_INVALID")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "start", "stop"))
    args = parser.parse_args()
    try:
        config = None
        if args.action == "start":
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
            if not raw or len(raw) > MAX_BYTES:
                raise ValueError("INVALID_TUN_PROFILE")
            config = json.loads(raw)
        result = query(args.action, config)
        print(json.dumps(result))
        return 0 if result["state"] != "rejected" else 1
    except (OSError, ValueError, json.JSONDecodeError):
        print(json.dumps({"state": "rejected",
                          "system_vpn_verified": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
