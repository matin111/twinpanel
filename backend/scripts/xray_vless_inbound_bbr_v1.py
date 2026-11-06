#!/usr/bin/env python3
"""Opt in only the three public TwinPanel VLESS inbound sockets to BBR.

Use --check first. --apply preserves all existing credentials, tunnel routes,
protocols, Xray identities, TLS certificates, and the system-wide TCP default.
Rollback is automatic if validation or Xray restart fails.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timezone

CONFIG = Path("/usr/local/etc/xray/config.json")
LOCK = Path("/run/twinpanel-xray-inbound-bbr.lock")
MODULE_LOAD = Path("/etc/modules-load.d/twinpanel-xray-bbr.conf")
PUBLIC = {
    "vless-ws-tls": ("ws", "tls"),
    "vless-xhttp-reality": ("xhttp", "reality"),
    "vless-tcp-tls": ("tcp", "tls"),
}


def targeted_config(document: dict) -> tuple[dict, bool, dict[str, int]]:
    result = copy.deepcopy(document)
    seen: dict[str, int] = {}
    changed = False
    for inbound in result.get("inbounds", []):
        if not isinstance(inbound, dict):
            continue
        tag = str(inbound.get("tag") or "")
        if tag not in PUBLIC:
            continue
        stream = inbound.get("streamSettings")
        expected_network, expected_security = PUBLIC[tag]
        if (
            inbound.get("protocol") != "vless"
            or not isinstance(stream, dict)
            or stream.get("network") != expected_network
            or stream.get("security") != expected_security
        ):
            raise RuntimeError("unexpected public VLESS inbound definition: " + tag)
        if tag in seen:
            raise RuntimeError("duplicate public VLESS inbound: " + tag)
        seen[tag] = int(inbound.get("port") or 0)
        if not 1 <= seen[tag] <= 65535:
            raise RuntimeError("invalid public inbound port: " + tag)
        sockopts = stream.setdefault("sockopt", {})
        if not isinstance(sockopts, dict):
            raise RuntimeError("non-object sockopt on " + tag)
        existing = sockopts.get("tcpCongestion")
        if existing not in (None, "", "bbr"):
            raise RuntimeError("custom congestion policy exists on " + tag)
        if existing != "bbr":
            sockopts["tcpCongestion"] = "bbr"
            changed = True
    if set(seen) != set(PUBLIC):
        raise RuntimeError("public VLESS inbound set incomplete")
    return result, changed, seen


def command(*args: str, timeout: int = 20) -> None:
    subprocess.run(args, check=True, timeout=timeout, stdout=subprocess.DEVNULL)


def is_active() -> bool:
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", "xray"], check=False, timeout=8
    ).returncode == 0


def check_listeners(ports: dict[str, int], timeout: float = 18) -> bool:
    """Wait for Xray's asynchronous listeners to bind after systemd restart."""
    deadline = time.monotonic() + timeout
    while True:
        ready = is_active()
        for port in ports.values():
            if not ready:
                break
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
            except OSError:
                ready = False
                break
        if ready:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.4)


def run(apply: bool) -> None:
    initial = CONFIG.read_bytes()
    source = json.loads(initial)
    prepared, changed, ports = targeted_config(source)
    print("VLESS_ONLY_BBR", "change_needed" if changed else "already_set", "ports", ports)
    if not apply or not changed:
        return
    if os.geteuid() != 0:
        raise RuntimeError("--apply requires root")
    if not is_active():
        raise RuntimeError("Xray is not active; refusing update")
    # Load BBR without changing net.ipv4.tcp_congestion_control for other apps.
    command("modprobe", "tcp_bbr", timeout=10)
    available = Path("/proc/sys/net/ipv4/tcp_available_congestion_control").read_text()
    if "bbr" not in available.split():
        raise RuntimeError("kernel BBR not supported")
    metadata = CONFIG.stat()
    stage = None
    backup = CONFIG.with_name(
        CONFIG.name + ".before-vless-bbr-" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=str(CONFIG.parent),
            prefix="tp-vless-bbr-", suffix=".json", delete=False,
        ) as stream:
            stage = Path(stream.name)
            json.dump(prepared, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.chown(stage, metadata.st_uid, metadata.st_gid)
        os.chmod(stage, stat.S_IMODE(metadata.st_mode))
        command("/usr/local/bin/xray", "run", "-test", "-config", str(stage))
        if CONFIG.read_bytes() != initial:
            raise RuntimeError("Xray config changed during staging")
        shutil.copy2(CONFIG, backup)
        os.chmod(backup, 0o600)
        os.replace(stage, CONFIG)
        stage = None
        try:
            command("systemctl", "restart", "xray", timeout=25)
            if not check_listeners(ports):
                raise RuntimeError("Xray health/listener check failed")
        except Exception:
            # Restore original config atomically, then bring back original Xray.
            os.chown(backup, metadata.st_uid, metadata.st_gid)
            os.chmod(backup, stat.S_IMODE(metadata.st_mode))
            os.replace(backup, CONFIG)
            command("systemctl", "restart", "xray", timeout=25)
            raise
        # Module availability persists across node reboots; TCP default unchanged.
        if not MODULE_LOAD.exists():
            MODULE_LOAD.write_text("tcp_bbr\n", encoding="ascii")
        print("VLESS_ONLY_BBR applied", "xray=active", "backup=" + backup.name)
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.check == args.apply:
        parser.error("choose exactly one of --check or --apply")
    with LOCK.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        run(apply=args.apply)
