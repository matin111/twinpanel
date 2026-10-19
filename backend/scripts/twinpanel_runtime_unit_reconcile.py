#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_RELEASE_ROOT = Path("/opt/twinpanel/current")
DEFAULT_API_UNIT = Path("/etc/systemd/system/twinpanel-api.service")
DEFAULT_API_UNIT_BACKUP = Path(
    "/etc/systemd/system/twinpanel-api.service.pre-runtime-convergence"
)
DEFAULT_STATE_FILE = Path(
    "/var/lib/twinpanel-license/runtime-unit-reconcile.json"
)
DEFAULT_SYSTEMCTL = "/usr/bin/systemctl"
INFLIGHT_RESTART_GRACE_SECONDS = 12.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return values

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def detect_api_port() -> int:
    values: dict[str, str] = {}
    for path in (
        Path("/etc/twinpanel/install.env"),
        Path("/etc/twinpanel/backend.env"),
        Path("/etc/twinpanel/frontend.env"),
    ):
        values.update(_env_file(path))

    raw = str(
        values.get("TWINPANEL_API_PORT")
        or os.getenv("TWINPANEL_API_PORT")
        or ""
    ).strip()
    if raw.isdigit():
        port = int(raw)
        if 1 <= port <= 65535:
            return port

    backend_url = str(
        values.get("TWINPANEL_BACKEND_URL")
        or os.getenv("TWINPANEL_BACKEND_URL")
        or ""
    ).strip()
    if backend_url:
        try:
            parsed = urlparse(backend_url)
            if parsed.port and 1 <= int(parsed.port) <= 65535:
                return int(parsed.port)
        except (TypeError, ValueError):
            pass

    return 8095


def render_api_unit(release_root: Path, api_port: int) -> str:
    if not 1 <= int(api_port) <= 65535:
        raise RuntimeError("API_PORT_INVALID")

    template = release_root / "deploy/systemd/twinpanel-api.service.tpl"
    if not template.is_file():
        raise RuntimeError("API_SERVICE_TEMPLATE_MISSING")

    content = template.read_text(encoding="utf-8").replace(
        "__API_PORT__",
        str(int(api_port)),
    )
    if "__API_PORT__" in content:
        raise RuntimeError("API_SERVICE_TEMPLATE_PORT_UNRESOLVED")
    if "WorkingDirectory=/opt/twinpanel/current/backend" not in content:
        raise RuntimeError("API_SERVICE_TEMPLATE_CURRENT_PATH_MISSING")
    if "ExecStart=/opt/twinpanel/venv/bin/uvicorn app.main:app" not in content:
        raise RuntimeError("API_SERVICE_TEMPLATE_EXEC_INVALID")
    return content.rstrip() + "\n"


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


def _run(
    argv: list[str],
    *,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
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


def _main_pid(systemctl: str, unit_name: str) -> int:
    result = _run(
        [systemctl, "show", unit_name, "--property=MainPID", "--value"],
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


def _expected_backend(active_root: Path) -> Path:
    return (active_root / "backend").resolve(strict=True)


def api_process_matches_active_release(
    *,
    active_root: Path,
    systemctl: str,
    unit_name: str = "twinpanel-api.service",
) -> tuple[bool, int, str | None]:
    expected = _expected_backend(active_root)
    pid = _main_pid(systemctl, unit_name)
    cwd = _pid_cwd(pid)
    return bool(cwd and cwd == expected), pid, str(cwd) if cwd else None


def wait_for_api_process_match(
    *,
    active_root: Path,
    systemctl: str,
    seconds: float = 30.0,
) -> tuple[int, str]:
    deadline = time.monotonic() + max(1.0, float(seconds))
    last_pid = 0
    last_cwd: str | None = None

    while time.monotonic() < deadline:
        ok, pid, cwd = api_process_matches_active_release(
            active_root=active_root,
            systemctl=systemctl,
        )
        last_pid = pid
        last_cwd = cwd
        if ok and cwd:
            return pid, cwd
        time.sleep(0.25)

    raise RuntimeError(
        "API_RUNTIME_PATH_MISMATCH:"
        f"pid={last_pid}:cwd={last_cwd or 'none'}:"
        f"expected={_expected_backend(active_root)}"
    )


def reconcile_api_unit(
    *,
    release_root: Path,
    api_port: int,
    unit_path: Path = DEFAULT_API_UNIT,
    backup_path: Path = DEFAULT_API_UNIT_BACKUP,
    restart: bool = False,
    verify: bool = False,
    systemctl: str | None = None,
) -> dict[str, object]:
    release_root = release_root.resolve(strict=True)
    expected = render_api_unit(release_root, api_port)

    try:
        previous = unit_path.read_text(encoding="utf-8")
    except OSError:
        previous = ""

    changed = previous != expected
    if changed:
        if previous and not backup_path.exists():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_text(previous, encoding="utf-8")
            os.chmod(backup_path, 0o644)
        _atomic_write(unit_path, expected, 0o644)

    ctl = systemctl or _systemctl_path()
    if changed:
        result = _run([ctl, "daemon-reload"], timeout=20)
        if result.returncode != 0:
            raise RuntimeError(
                "SYSTEMD_DAEMON_RELOAD_FAILED:"
                + (result.stdout or "")[-500:].replace("\n", " ")
            )

    process_matches = False
    pid = 0
    cwd: str | None = None
    if restart or verify:
        process_matches, pid, cwd = api_process_matches_active_release(
            active_root=release_root,
            systemctl=ctl,
        )

    restarted = False
    reused_inflight_restart = False
    if restart and not process_matches:
        # If the unit itself changed, any API restart that was queued before
        # daemon-reload cannot be trusted to converge onto the new canonical
        # runtime. Waiting for that stale transaction wastes the updater's
        # health window and is exactly how migrated/legacy installs can end up
        # with POST_UPDATE_HEALTH_VERSION_FAILED:api,web. In that case dispatch
        # one recovery restart immediately from the freshly loaded unit.
        #
        # If the unit was already canonical, the updater may simply have an API
        # restart in flight. Reuse that restart first and only dispatch one
        # recovery restart when the bounded grace really expires.
        if not changed:
            try:
                pid, cwd = wait_for_api_process_match(
                    active_root=release_root,
                    systemctl=ctl,
                    seconds=INFLIGHT_RESTART_GRACE_SECONDS,
                )
                process_matches = True
                reused_inflight_restart = True
            except RuntimeError:
                pass

        if not process_matches:
            result = _run(
                [ctl, "--no-block", "restart", "twinpanel-api.service"],
                timeout=20,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "API_RESTART_FAILED:"
                    + (result.stdout or "")[-500:].replace("\n", " ")
                )
            restarted = True

    if verify:
        pid, cwd = wait_for_api_process_match(
            active_root=release_root,
            systemctl=ctl,
            seconds=30,
        )
        process_matches = True

    return {
        "ok": True,
        "checked_at": _now(),
        "release_root": str(release_root),
        "api_port": int(api_port),
        "unit_path": str(unit_path),
        "unit_changed": changed,
        "api_restarted": restarted,
        "api_reused_inflight_restart": reused_inflight_restart,
        "api_process_matches_active_release": process_matches,
        "api_pid": pid,
        "api_cwd": cwd,
    }


def _write_state(payload: dict[str, object], state_path: Path) -> None:
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            state_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            0o600,
        )
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Converge TwinPanel API systemd runtime to the active release",
    )
    parser.add_argument(
        "--release-root",
        default=str(DEFAULT_RELEASE_ROOT),
    )
    parser.add_argument("--api-port", type=int, default=None)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_FILE),
    )
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        print("RUNTIME_UNIT_RECONCILE_REQUIRES_ROOT", file=sys.stderr)
        return 2

    release_root = Path(args.release_root)
    state_path = Path(args.state_file)
    api_port = int(args.api_port or detect_api_port())

    try:
        result = reconcile_api_unit(
            release_root=release_root,
            api_port=api_port,
            restart=bool(args.restart),
            verify=bool(args.verify),
        )
        _write_state(result, state_path)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        failed = {
            "ok": False,
            "checked_at": _now(),
            "release_root": str(release_root),
            "api_port": api_port,
            "error": str(exc)[:1200],
        }
        _write_state(failed, state_path)
        print(json.dumps(failed, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
