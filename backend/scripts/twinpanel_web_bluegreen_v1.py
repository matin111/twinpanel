#!/usr/bin/env python3
"""Opt-in, fail-closed TwinPanel Web blue/green release router.

Only updater invokes this. The legacy web service is not restarted during
candidate preparation or Nginx cutover. Never touch API or user data here.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

STATE = Path("/var/lib/twinpanel-license/web-slot-state.json")
SLOT_UNIT = Path("/etc/systemd/system/twinpanel-web-slot@.service")
ENV_DIR = Path("/etc/twinpanel")
ENABLED = Path("/etc/nginx/sites-enabled")
ALLOWED_PORTS = (3000, 3001)
UPSTREAM = re.compile(r"http://127\\.0\\.0\\.1:(3000|3001)(?=[/;])")
VERSION = re.compile(r"^\\d+\\.\\d+\\.\\d+(?:-[A-Za-z0-9._-]+)?$")
UNIT = """[Unit]
Description=TwinPanel pinned Next.js Web slot %i
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=www-data
Group=www-data
Environment=NODE_ENV=production
EnvironmentFile=/etc/twinpanel/frontend.env
EnvironmentFile=/etc/twinpanel/web-slot-%i.env
WorkingDirectory=/opt/twinpanel
ExecStart=/bin/bash -lc 'cd "$TP_WEB_RELEASE/.next/standalone" && exec env HOSTNAME=127.0.0.1 PORT="$TP_WEB_PORT" /usr/bin/node server.js'
Restart=always
RestartSec=4
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
"""


def cmd(*args: str, timeout: int = 25) -> None:
    subprocess.run(args, check=True, timeout=timeout, stdout=subprocess.DEVNULL)


def versioned_release(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if resolved.parent != Path("/opt/twinpanel/releases") or not VERSION.fullmatch(resolved.name):
        raise RuntimeError("WEB_RELEASE_NOT_PINNED")
    if not (resolved / ".next/standalone/server.js").is_file():
        raise RuntimeError("WEB_STANDALONE_MISSING")
    return resolved


def nginx_targets() -> list[Path]:
    """Only regular files resolved from enabled vhosts, not arbitrary configs."""
    paths: set[Path] = set()
    for link in ENABLED.iterdir():
        target = link.resolve(strict=True)
        if not target.is_file() or not str(target).startswith("/etc/nginx/"):
            raise RuntimeError("WEB_NGINX_TARGET_UNSAFE")
        if target.suffix not in ("", ".conf"):
            continue
        paths.add(target)
    return sorted(paths)


def referenced_ports(paths: list[Path]) -> set[int]:
    ports = set()
    for path in paths:
        ports.update(int(x) for x in UPSTREAM.findall(path.read_text()))
    return ports


def read_state() -> dict:
    try:
        state = json.loads(STATE.read_text())
    except FileNotFoundError:
        return {}
    if not isinstance(state, dict):
        raise RuntimeError("WEB_SLOT_STATE_INVALID")
    return state


def old_port() -> int:
    ports = referenced_ports(nginx_targets())
    if len(ports) != 1:
        raise RuntimeError("WEB_NGINX_MULTIPLE_OR_MISSING_UPSTREAMS")
    active = ports.pop()
    state = read_state()
    if state and state.get("active_port") != active:
        raise RuntimeError("WEB_SLOT_STATE_NGINX_DISAGREE")
    return active


def copy_previous_static(previous: Path, candidate: Path) -> None:
    """Keep old hashed JS/CSS assets reachable by existing browser tabs."""
    previous = versioned_release(previous)
    candidate = versioned_release(candidate)
    for rel in (".next/static", ".next/standalone/.next/static"):
        src = previous / rel
        dst = candidate / rel
        if not src.is_dir():
            continue
        for path in src.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            target = dst / path.relative_to(src)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def prepare(candidate: Path, previous: Path) -> tuple[int, int]:
    active = old_port()
    standby = 3001 if active == 3000 else 3000
    candidate = versioned_release(candidate)
    copy_previous_static(previous, candidate)
    if not SLOT_UNIT.exists() or SLOT_UNIT.read_text() != UNIT:
        _write_atomic(SLOT_UNIT, UNIT, 0o644)
    env_path = ENV_DIR / f"web-slot-{standby}.env"
    _write_atomic(env_path, f"TP_WEB_RELEASE={candidate}\\nTP_WEB_PORT={standby}\\n", 0o600)
    cmd("systemctl", "daemon-reload")
    unit = f"twinpanel-web-slot@{standby}.service"
    if subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0:
        raise RuntimeError("WEB_CANDIDATE_SLOT_ALREADY_ACTIVE")
    cmd("systemctl", "start", unit)
    return active, standby


def _write_atomic(path: Path, data: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".twinpanel-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _update_nginx(old: int, new: int) -> None:
    if old == new or old not in ALLOWED_PORTS or new not in ALLOWED_PORTS:
        raise RuntimeError("WEB_SLOT_PORT_INVALID")
    paths = nginx_targets()
    if referenced_ports(paths) != {old}:
        raise RuntimeError("WEB_NGINX_UPSTREAM_CHANGED")
    originals = {path: path.read_text() for path in paths}
    changed = {}
    for path, source in originals.items():
        target = UPSTREAM.sub(lambda m: m.group().replace(f":{old}", f":{new}"), source)
        if target != source:
            changed[path] = target
    if not changed:
        raise RuntimeError("WEB_NGINX_NO_MATCH")
    try:
        for path, target in changed.items():
            _write_atomic(path, target, path.stat().st_mode & 0o777)
        cmd("nginx", "-t")
        cmd("systemctl", "reload", "nginx")
    except Exception:
        for path, source in originals.items():
            if path in changed:
                _write_atomic(path, source, path.stat().st_mode & 0o777)
        cmd("nginx", "-t")
        cmd("systemctl", "reload", "nginx")
        raise


def activate(previous_port: int, candidate_port: int, release: Path) -> None:
    """Caller must already verify candidate direct health+version."""
    if old_port() != previous_port:
        raise RuntimeError("WEB_SLOT_UPSTREAM_RACE")
    _update_nginx(previous_port, candidate_port)
    try:
        _write_atomic(STATE, json.dumps({
            "active_port": candidate_port,
            "release": str(versioned_release(release)),
        }) + "\\n", 0o600)
    except Exception:
        _update_nginx(candidate_port, previous_port)
        raise


def revert(previous_port: int, candidate_port: int, old_release: Path) -> None:
    if old_port() == candidate_port:
        _update_nginx(candidate_port, previous_port)
    _write_atomic(STATE, json.dumps({
        "active_port": previous_port,
        "release": str(versioned_release(old_release)),
    }) + "\\n", 0o600)


def stop_unused(old: int, delay_seconds: int = 30) -> None:
    """Only retire an old slot after a successful cutover and drain."""
    time.sleep(delay_seconds)
    if old_port() == old:
        return
    if old == 3000 and subprocess.run(
        ["systemctl", "is-active", "--quiet", "twinpanel-web.service"]
    ).returncode == 0:
        cmd("systemctl", "stop", "twinpanel-web.service")
    else:
        cmd("systemctl", "stop", f"twinpanel-web-slot@{old}.service")
