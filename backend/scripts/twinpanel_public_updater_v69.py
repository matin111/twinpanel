#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

CORE_PATH = Path(__file__).with_name("twinpanel_public_updater.py")
API_HEALTH_SECONDS = 75
WEB_HEALTH_SECONDS = 45


def _load_core():
    spec = importlib.util.spec_from_file_location("twinpanel_public_updater_core_v69", CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("UPDATER_CORE_IMPORT_SPEC_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wait_one(core, url: str, expected_version: str, seconds: int) -> bool:
    deadline = time.monotonic() + max(1, int(seconds))
    while time.monotonic() < deadline:
        if core.health_ok(url, expected_version):
            return True
        time.sleep(0.5)
    return False


def _staged_wait_for_healthy(core, urls: dict[str, str], expected_version: str, seconds: int = 45):
    ordered: list[tuple[str, str]] = []
    for preferred in ("api", "web"):
        if preferred in urls:
            ordered.append((preferred, urls[preferred]))
    ordered.extend((name, url) for name, url in urls.items() if name not in {"api", "web"})

    for name, url in ordered:
        if name == "api":
            budget = API_HEALTH_SECONDS
        elif name == "web":
            budget = WEB_HEALTH_SECONDS
        else:
            budget = max(45, int(seconds))

        started = core.stage_begin()
        ok = _wait_one(core, url, expected_version, budget)
        core.stage_end(f"health_{name}", started)
        if not ok:
            return False, [name]

    return True, []


def _restore_updater_unit(previous: Path) -> bool:
    template = previous / "deploy/systemd/twinpanel-updater.service.tpl"
    if not template.is_file():
        return False
    path = Path("/etc/systemd/system/twinpanel-updater.service")
    tmp = path.with_suffix(".service.tmp")
    tmp.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(path)
    return True


def _install_rollback_unit_restore(core) -> None:
    original_rollback = core.rollback

    def rollback_with_unit_restore(previous: Path | None) -> None:
        if previous and previous.exists():
            try:
                env = core.runtime_env()
                web_port = int(env.get("TWINPANEL_WEB_PORT", "3000") or 3000)
                core.install_web_unit(previous, web_port)
                restored_updater = _restore_updater_unit(previous)
                print(
                    f"UPDATER_ROLLBACK_UNIT_RESTORE_V70 previous={previous} "
                    f"web=true updater={str(restored_updater).lower()}",
                    flush=True,
                )
            except Exception as exc:
                # Unit restoration is best-effort and must never prevent the
                # canonical symlink rollback/restart path from running.
                print(
                    f"UPDATER_ROLLBACK_UNIT_RESTORE_V70_WARNING {type(exc).__name__}:{exc}",
                    file=sys.stderr,
                    flush=True,
                )
        original_rollback(previous)

    core.rollback = rollback_with_unit_restore


def main() -> int:
    core = _load_core()
    core.wait_for_healthy = lambda urls, expected_version, seconds=45: _staged_wait_for_healthy(
        core,
        urls,
        expected_version,
        seconds,
    )
    _install_rollback_unit_restore(core)
    try:
        return int(core.main())
    except Exception as exc:
        core.save(state="failed", error=str(exc)[:1200])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
