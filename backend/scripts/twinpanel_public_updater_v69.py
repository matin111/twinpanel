#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
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


def main() -> int:
    core = _load_core()
    core.wait_for_healthy = lambda urls, expected_version, seconds=45: _staged_wait_for_healthy(
        core,
        urls,
        expected_version,
        seconds,
    )
    try:
        return int(core.main())
    except Exception as exc:
        core.save(state="failed", error=str(exc)[:1200])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
