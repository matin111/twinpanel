#!/usr/bin/env python3
"""Interactive Cisco authentication diagnostic, without a VPN or network route.

Always reads prompts from the terminal, never from the Python source heredoc.
Credentials are forwarded through stdin to the existing authentication-only
preflight. Do not print or persist secrets, cookies, or raw process output.
"""
from __future__ import annotations

import getpass
import json
from pathlib import Path
import subprocess
import sys


AUTH_SCRIPT = Path(__file__).with_name("cisco_openconnect_auth.py")


def collect_profile(input_fn=input, password_fn=getpass.getpass) -> dict:
    host = input_fn("Cisco server IP/domain: ").strip()
    port_text = input_fn("Port [443]: ").strip() or "443"
    if not port_text.isdecimal():
        raise ValueError("CISCO_PORT_INVALID")
    username = input_fn("Username: ").strip()
    password = password_fn("Password: ")
    return {"protocol": "cisco", "host": host, "port": int(port_text),
            "username": username, "password": password}


def check(profile: dict) -> dict:
    try:
        result = subprocess.run(
            [sys.executable, str(AUTH_SCRIPT), "authenticate"],
            input=json.dumps(profile), text=True, capture_output=True,
            timeout=50, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"state": "error", "reason": "CISCO_AUTH_TIMEOUT",
                "vpn_connected": False}
    except OSError:
        return {"state": "error", "reason": "CISCO_PREFLIGHT_FAILED",
                "vpn_connected": False}
    try:
        reply = json.loads(result.stdout)
        if isinstance(reply, dict) and reply.get("state") in {
            "error", "cisco_authentication_verified"
        }:
            return reply
    except (ValueError, TypeError):
        pass
    return {"state": "error", "reason": "CISCO_PREFLIGHT_FAILED",
            "vpn_connected": False}


def main() -> int:
    try:
        profile = collect_profile()
        result = check(profile)
    except (EOFError, KeyboardInterrupt):
        result = {"state": "error", "reason": "CISCO_INPUT_CANCELLED",
                  "vpn_connected": False}
    except ValueError:
        result = {"state": "error", "reason": "CISCO_PORT_INVALID",
                  "vpn_connected": False}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result.get("state") == "cisco_authentication_verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
