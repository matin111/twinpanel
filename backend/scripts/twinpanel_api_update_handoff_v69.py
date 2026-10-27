#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

CURRENT = Path("/opt/twinpanel/current")
UPDATE_STATE = Path("/var/lib/twinpanel-license/update-state.json")
UNIT = "twinpanel-api.service"
GRACE_SECONDS = 2.0
SETTLE_SECONDS = 5.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_state() -> dict:
    try:
        value = json.loads(UPDATE_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _main_pid() -> int:
    cp = subprocess.run(
        ["systemctl", "show", UNIT, "--property=MainPID", "--value"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    raw = (cp.stdout or "").strip()
    return int(raw) if cp.returncode == 0 and raw.isdigit() else 0


def _cwd(pid: int) -> Path | None:
    if pid <= 0:
        return None
    try:
        return Path(f"/proc/{pid}/cwd").resolve(strict=True)
    except OSError:
        return None


def _expected_backend() -> Path:
    return (CURRENT / "backend").resolve(strict=True)


def _active_version() -> str:
    try:
        return (CURRENT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _safe_stale_runtime(pid: int, expected: Path) -> tuple[bool, Path | None]:
    cwd = _cwd(pid)
    if cwd is None or cwd == expected:
        return False, cwd
    releases = Path("/opt/twinpanel/releases").resolve()
    try:
        cwd.relative_to(releases)
    except ValueError:
        return False, cwd
    return True, cwd


def main() -> int:
    if os.geteuid() != 0:
        raise RuntimeError("API_UPDATE_HANDOFF_REQUIRES_ROOT")

    state = _read_state()
    active_version = _active_version()
    target_version = str(state.get("target_version") or "").strip()
    if str(state.get("state") or "").strip().lower() != "restarting":
        print(json.dumps({"ok": True, "skipped": "not_restarting"}, separators=(",", ":")))
        return 0
    if not active_version or target_version != active_version:
        print(json.dumps({"ok": True, "skipped": "target_mismatch"}, separators=(",", ":")))
        return 0

    expected = _expected_backend()
    deadline = time.monotonic() + GRACE_SECONDS
    first_pid = 0
    first_cwd: Path | None = None

    while time.monotonic() < deadline:
        pid = _main_pid()
        stale, cwd = _safe_stale_runtime(pid, expected)
        if pid <= 0 or cwd == expected:
            print(json.dumps({
                "ok": True,
                "checked_at": _now(),
                "forced": False,
                "api_pid": pid,
                "api_cwd": str(cwd) if cwd else None,
            }, separators=(",", ":")))
            return 0
        if not stale:
            print(json.dumps({
                "ok": True,
                "skipped": "unmanaged_runtime",
                "api_pid": pid,
                "api_cwd": str(cwd) if cwd else None,
            }, separators=(",", ":")))
            return 0
        first_pid = pid
        first_cwd = cwd
        time.sleep(0.2)

    pid = _main_pid()
    stale, cwd = _safe_stale_runtime(pid, expected)
    if not stale or pid <= 0:
        print(json.dumps({"ok": True, "forced": False, "api_pid": pid}, separators=(",", ":")))
        return 0
    if first_pid and pid != first_pid:
        print(json.dumps({"ok": True, "skipped": "pid_changed", "api_pid": pid}, separators=(",", ":")))
        return 0
    if first_cwd is not None and cwd != first_cwd:
        print(json.dumps({"ok": True, "skipped": "cwd_changed", "api_pid": pid}, separators=(",", ":")))
        return 0

    os.kill(pid, signal.SIGKILL)

    settle_deadline = time.monotonic() + SETTLE_SECONDS
    while time.monotonic() < settle_deadline:
        current_pid = _main_pid()
        if current_pid != pid:
            break
        time.sleep(0.1)

    print(json.dumps({
        "ok": True,
        "checked_at": _now(),
        "forced": True,
        "terminated_pid": pid,
        "terminated_cwd": str(cwd) if cwd else None,
        "expected_backend": str(expected),
    }, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
