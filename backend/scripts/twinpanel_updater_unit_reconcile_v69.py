#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

CURRENT = Path("/opt/twinpanel/current")
TEMPLATE = CURRENT / "deploy/systemd/twinpanel-updater.service.tpl"
UNIT = Path("/etc/systemd/system/twinpanel-updater.service")
BACKUP = Path("/etc/systemd/system/twinpanel-updater.service.pre-v69")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
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


def main() -> int:
    if os.geteuid() != 0:
        raise RuntimeError("UPDATER_UNIT_RECONCILE_REQUIRES_ROOT")
    if not TEMPLATE.is_file():
        raise RuntimeError("UPDATER_UNIT_TEMPLATE_MISSING")

    expected = TEMPLATE.read_text(encoding="utf-8").rstrip() + "\n"
    if "twinpanel_public_updater_v69.py" not in expected:
        raise RuntimeError("UPDATER_UNIT_V69_EXEC_MISSING")
    if "WorkingDirectory=/opt/twinpanel/current/backend" not in expected:
        raise RuntimeError("UPDATER_UNIT_CURRENT_PATH_MISSING")

    previous = UNIT.read_text(encoding="utf-8") if UNIT.is_file() else ""
    changed = previous != expected

    if changed:
        if previous and not BACKUP.exists():
            BACKUP.write_text(previous, encoding="utf-8")
            os.chmod(BACKUP, 0o644)
        _atomic_write(UNIT, expected)
        cp = subprocess.run(
            ["systemctl", "daemon-reload"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=20,
        )
        if cp.returncode != 0:
            raise RuntimeError("UPDATER_UNIT_DAEMON_RELOAD_FAILED:" + (cp.stdout or "")[-500:])

    print(json.dumps({
        "ok": True,
        "checked_at": _now(),
        "changed": changed,
        "unit": str(UNIT),
        "exec_v69": True,
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
