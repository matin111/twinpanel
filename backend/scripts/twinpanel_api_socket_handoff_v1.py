#!/usr/bin/env python3
"""Opt-in, reversible systemd socket handoff for TwinPanel's single-worker API.

This does NOT run automatically on install or update. Normal API service mode
remains unchanged until an operator explicitly applies this after a canary.
The persistent socket owns 127.0.0.1:<api-port> while Uvicorn restarts, so
Nginx connections can queue rather than receiving immediate ECONNREFUSED.
Requests already in flight may still fail; this is not a zero-downtime claim.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path

CURRENT = Path("/opt/twinpanel/current")
ENV_FILE = Path("/etc/twinpanel/backend.env")
SOCKET_UNIT = Path("/etc/systemd/system/twinpanel-api.socket")
OVERRIDE = Path("/etc/systemd/system/twinpanel-api.service.d/90-socket-handoff.conf")
API_UNIT = "twinpanel-api.service"
SOCKET_NAME = "twinpanel-api.socket"


def api_port(env_path: Path = ENV_FILE) -> int:
    port = 8095
    if env_path.is_file():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("TWINPANEL_API_PORT="):
                value = line.partition("=")[2].strip().strip('"').strip("'")
                if not value.isdigit():
                    raise RuntimeError("API_SOCKET_PORT_INVALID")
                port = int(value)
    if not 1 <= port <= 65535:
        raise RuntimeError("API_SOCKET_PORT_OUT_OF_RANGE")
    return port


def socket_unit(port: int) -> str:
    if not 1 <= int(port) <= 65535:
        raise ValueError("API_SOCKET_PORT_INVALID")
    return (
        "[Unit]\n"
        "Description=TwinPanel API persistent listener during service restart\n"
        "[Socket]\n"
        "ListenStream=127.0.0.1:" + str(int(port)) + "\n"
        "Accept=no\n"
        "Backlog=2048\n"
        "NoDelay=true\n"
        "Service=twinpanel-api.service\n"
        "[Install]\n"
        "WantedBy=sockets.target\n"
    )


def service_override() -> str:
    # The base service is still source-controlled by runtime_unit_reconcile.
    # A drop-in survives its rewriting of the main API unit on an upgrade.
    return (
        "[Unit]\n"
        "Requires=twinpanel-api.socket\n"
        "After=twinpanel-api.socket\n"
        "[Service]\n"
        "Sockets=twinpanel-api.socket\n"
        "ExecStart=\n"
        "ExecStart=/opt/twinpanel/venv/bin/uvicorn app.main:app "
        "--fd 3 --workers 1\n"
    )


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", *args], check=check, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=45,
    )


def is_active(name: str) -> bool:
    return run("is-active", "--quiet", name, check=False).returncode == 0


def ensure_safe_state() -> tuple[int, str]:
    if os.geteuid() != 0:
        raise RuntimeError("API_SOCKET_ROOT_REQUIRED")
    if is_active("twinpanel-updater.service"):
        raise RuntimeError("API_SOCKET_UPDATER_IN_PROGRESS")
    version = (CURRENT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?", version):
        raise RuntimeError("API_SOCKET_RELEASE_UNRECOGNIZED")
    port = api_port()
    if not Path("/etc/systemd/system/twinpanel-api.service").is_file():
        raise RuntimeError("API_SOCKET_BASE_UNIT_MISSING")
    # Never replace or delete an independently managed socket or override.
    for path, expected in ((SOCKET_UNIT, socket_unit(port)),
                           (OVERRIDE, service_override())):
        if path.exists() and path.read_text(encoding="utf-8") != expected:
            raise RuntimeError("API_SOCKET_UNOWNED_CONFIGURATION:" + path.name)
    # A different drop-in overriding ExecStart or socket inheritance could
    # silently defeat the handoff; require explicit review instead.
    for folder in (Path("/etc/systemd/system/twinpanel-api.service.d"),):
        if folder.is_dir():
            for path in folder.glob("*.conf"):
                if path == OVERRIDE:
                    continue
                value = path.read_text(encoding="utf-8", errors="replace")
                if re.search(r"(?m)^\s*(ExecStart|Sockets)\s*=", value):
                    raise RuntimeError("API_SOCKET_CONFLICTING_DROPIN:" + path.name)
    return port, version


def atomic_write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp-" + str(os.getpid()))
    try:
        tmp.write_text(body, encoding="utf-8")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def check_health(port: int, version: str, seconds: float = 75.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:" + str(port) + "/health", timeout=2
            ) as response:
                body = json.loads(response.read(32768).decode("utf-8"))
            if response.status == 200 and body.get("ok") is True and body.get("version") == version:
                return True
        except (OSError, ValueError, TypeError, KeyError):
            pass
        time.sleep(0.5)
    return False


def enable(port: int, version: str) -> None:
    if SOCKET_UNIT.exists() or OVERRIDE.exists():
        # Repeated applies never restart a healthy service.
        if not (SOCKET_UNIT.is_file() and OVERRIDE.is_file()
                and is_active(SOCKET_NAME) and is_active(API_UNIT)
                and check_health(port, version, seconds=3)):
            raise RuntimeError("API_SOCKET_PARTIAL_STATE_REQUIRES_REVIEW")
        print("API_SOCKET_ALREADY_ENABLED_AND_HEALTHY")
        return

    was_running = is_active(API_UNIT)
    if not was_running or not check_health(port, version, seconds=3):
        raise RuntimeError("API_SOCKET_PRECHANGE_HEALTH_FAILED")

    staged = False
    try:
        atomic_write(SOCKET_UNIT, socket_unit(port))
        atomic_write(OVERRIDE, service_override())
        staged = True
        run("daemon-reload")
        # First opt-in needs one controlled API stop to release the existing
        # bind. Subsequent release upgrades keep this socket open.
        run("stop", API_UNIT)
        run("enable", "--now", SOCKET_NAME)
        run("start", API_UNIT)
        if not check_health(port, version):
            raise RuntimeError("API_SOCKET_HEALTH_GATE_FAILED")
        print("API_SOCKET_ENABLED_HEALTHY version=" + version)
    except BaseException:
        # Fail back to the unchanged normal bind-mode API, never touch DB/VPN.
        if staged:
            run("stop", API_UNIT, check=False)
            run("disable", "--now", SOCKET_NAME, check=False)
        OVERRIDE.unlink(missing_ok=True)
        SOCKET_UNIT.unlink(missing_ok=True)
        run("daemon-reload", check=False)
        if was_running:
            run("start", API_UNIT, check=False)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Opt in to a controlled API restart (not automatic)")
    parser.add_argument("--confirm-brief-cutover", action="store_true",
                        help="Required acknowledgement of initial cutover downtime")
    args = parser.parse_args(argv)
    port, version = ensure_safe_state()
    if not args.apply:
        print(json.dumps({"mode": "read_only", "api_port": port,
                          "version": version, "socket_exists": SOCKET_UNIT.exists(),
                          "override_exists": OVERRIDE.exists(),
                          "updater_active": False}, sort_keys=True))
        return 0
    if not args.confirm_brief_cutover:
        parser.error("--apply requires --confirm-brief-cutover")
    enable(port, version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
