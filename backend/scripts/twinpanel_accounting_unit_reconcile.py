#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


DEFAULT_RELEASE_ROOT = Path("/opt/twinpanel/current")
DEFAULT_UNIT_PATH = Path("/etc/systemd/system/twinpanel-modern-accounting.service")
DEFAULT_SYSTEMCTL = "/usr/bin/systemctl"
UNIT_NAME = "twinpanel-modern-accounting.service"


def _run(argv: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )


def _systemctl_path() -> str:
    configured = str(os.getenv("TWINPANEL_SYSTEMCTL") or "").strip()
    if configured:
        return configured
    if Path(DEFAULT_SYSTEMCTL).is_file():
        return DEFAULT_SYSTEMCTL
    found = shutil.which("systemctl")
    if not found:
        raise RuntimeError("SYSTEMCTL_NOT_FOUND")
    return found


def _atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def render_unit(release_root: Path) -> str:
    template = release_root / "deploy/systemd/twinpanel-modern-accounting.service.tpl"
    worker = release_root / "backend/scripts/twinpanel_modern_accounting_worker.py"
    if not template.is_file():
        raise RuntimeError("ACCOUNTING_SERVICE_TEMPLATE_MISSING")
    if not worker.is_file():
        raise RuntimeError("ACCOUNTING_WORKER_MISSING")

    content = template.read_text(encoding="utf-8").rstrip() + "\n"
    required = (
        "WorkingDirectory=/opt/twinpanel/current/backend",
        "ExecStart=/opt/twinpanel/venv/bin/python3 /opt/twinpanel/current/backend/scripts/twinpanel_modern_accounting_worker.py",
        "EnvironmentFile=/etc/twinpanel/backend.env",
    )
    for marker in required:
        if marker not in content:
            raise RuntimeError(f"ACCOUNTING_SERVICE_TEMPLATE_INVALID:{marker}")
    return content


def _main_pid(systemctl: str) -> int:
    result = _run(
        [systemctl, "show", UNIT_NAME, "--property=MainPID", "--value"],
        timeout=8,
    )
    if result.returncode != 0:
        return 0
    raw = (result.stdout or "").strip()
    return int(raw) if raw.isdigit() else 0


def _pid_cwd(pid: int) -> Path | None:
    if pid <= 0:
        return None
    try:
        return Path(f"/proc/{pid}/cwd").resolve(strict=True)
    except OSError:
        return None


def _expected_backend(release_root: Path) -> Path:
    return (release_root / "backend").resolve(strict=True)


def process_matches_release(
    *,
    release_root: Path,
    systemctl: str,
) -> tuple[bool, int, str | None]:
    expected = _expected_backend(release_root)
    pid = _main_pid(systemctl)
    cwd = _pid_cwd(pid)
    return bool(cwd and cwd == expected), pid, str(cwd) if cwd else None


def _wait_for_match(
    *,
    release_root: Path,
    systemctl: str,
    seconds: float = 20.0,
) -> tuple[int, str]:
    deadline = time.monotonic() + max(1.0, float(seconds))
    last_pid = 0
    last_cwd: str | None = None
    while time.monotonic() < deadline:
        ok, pid, cwd = process_matches_release(
            release_root=release_root,
            systemctl=systemctl,
        )
        last_pid = pid
        last_cwd = cwd
        if ok and cwd:
            active = _run([systemctl, "is-active", UNIT_NAME], timeout=5)
            if active.returncode == 0 and (active.stdout or "").strip() == "active":
                return pid, cwd
        time.sleep(0.25)
    raise RuntimeError(
        "ACCOUNTING_RUNTIME_PATH_MISMATCH:"
        f"pid={last_pid}:cwd={last_cwd or 'none'}:"
        f"expected={_expected_backend(release_root)}"
    )


def reconcile(
    *,
    release_root: Path,
    unit_path: Path = DEFAULT_UNIT_PATH,
    verify: bool = False,
    systemctl: str | None = None,
) -> dict[str, object]:
    release_root = release_root.resolve(strict=True)
    expected = render_unit(release_root)
    ctl = systemctl or _systemctl_path()

    try:
        previous = unit_path.read_text(encoding="utf-8")
    except OSError:
        previous = ""

    changed = previous != expected
    if changed:
        _atomic_write(unit_path, expected, 0o644)
        result = _run([ctl, "daemon-reload"], timeout=20)
        if result.returncode != 0:
            raise RuntimeError(
                "ACCOUNTING_DAEMON_RELOAD_FAILED:"
                + (result.stdout or "")[-500:].replace("\n", " ")
            )

    enabled = _run([ctl, "enable", UNIT_NAME], timeout=20)
    if enabled.returncode != 0:
        raise RuntimeError(
            "ACCOUNTING_ENABLE_FAILED:"
            + (enabled.stdout or "")[-500:].replace("\n", " ")
        )

    matches, pid, cwd = process_matches_release(
        release_root=release_root,
        systemctl=ctl,
    )
    active = _run([ctl, "is-active", UNIT_NAME], timeout=5)
    is_active = active.returncode == 0 and (active.stdout or "").strip() == "active"

    restarted = False
    if changed or not matches or not is_active:
        result = _run([ctl, "restart", UNIT_NAME], timeout=25)
        if result.returncode != 0:
            raise RuntimeError(
                "ACCOUNTING_RESTART_FAILED:"
                + (result.stdout or "")[-800:].replace("\n", " ")
            )
        restarted = True
        pid, cwd = _wait_for_match(
            release_root=release_root,
            systemctl=ctl,
        )
        matches = True
        is_active = True
    elif verify:
        pid, cwd = _wait_for_match(
            release_root=release_root,
            systemctl=ctl,
            seconds=8.0,
        )

    return {
        "ok": bool(matches and is_active),
        "unit": UNIT_NAME,
        "changed": changed,
        "restarted": restarted,
        "pid": pid,
        "cwd": cwd,
        "expected_cwd": str(_expected_backend(release_root)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", default=str(DEFAULT_RELEASE_ROOT))
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    result = reconcile(
        release_root=Path(args.release_root),
        verify=bool(args.verify),
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
