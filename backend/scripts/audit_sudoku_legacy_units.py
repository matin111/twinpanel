#!/usr/bin/env python3
"""Read-only inventory of retired TwinPanel per-subscription Sudoku services.

No customer config, credentials, key material or database content is read.
Never modifies systemd, files, database, network or running processes.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

LEGACY_UNIT = re.compile(r"^twinpanel-sudoku-sub-([1-9][0-9]*)\.service$")


def _service_state(unit: str) -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    lines = result.stdout.strip().splitlines()
    return lines[0] if lines else "unknown"


def audit(unit_dir: Path, subscription_dir: Path, *, probe_systemd: bool = True) -> dict:
    """Scan owned unit names and numbered config directory names, not their contents."""
    units: dict[int, Path] = {}
    if unit_dir.is_dir():
        for entry in unit_dir.iterdir():
            match = LEGACY_UNIT.fullmatch(entry.name)
            if match and entry.is_file() and not entry.is_symlink():
                units[int(match.group(1))] = entry
    directories: set[int] = set()
    if subscription_dir.is_dir():
        for entry in subscription_dir.iterdir():
            if (entry.name.isascii() and entry.name.isdecimal()
                    and int(entry.name) > 0 and entry.is_dir() and not entry.is_symlink()):
                directories.add(int(entry.name))
    entries = []
    for sid in sorted(set(units) | directories):
        unit = units.get(sid)
        entries.append({
            "subscription_id": sid,
            "unit_present": unit is not None,
            "config_directory_present": sid in directories,
            "unit_mtime_utc": (
                datetime.fromtimestamp(unit.stat().st_mtime, timezone.utc).isoformat()
                if unit else None
            ),
            "service_state": (
                _service_state(unit.name) if (unit and probe_systemd) else "not_checked"
            ),
        })
    return {
        "legacy_count": len(entries),
        "legacy_units": len(units),
        "legacy_config_directories": len(directories),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-dir", type=Path, default=Path("/etc/systemd/system"))
    parser.add_argument(
        "--subscription-dir", type=Path,
        default=Path("/etc/twinpanel/standalone/sudoku/subscriptions"),
    )
    parser.add_argument("--no-systemd", action="store_true")
    args = parser.parse_args()
    report = audit(args.unit_dir, args.subscription_dir, probe_systemd=not args.no_systemd)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 2 if report["legacy_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
