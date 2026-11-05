#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import base64
import re
import urllib.request
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

    # /health alone cannot prove the subscription is usable.
    test_subscription_id = os.environ.get(
        "TWINPANEL_UPDATE_V2RAY_SMOKE_SUBSCRIPTION_ID", ""
    ).strip()
    if test_subscription_id:
        started = core.stage_begin()
        port = int(os.environ.get("TWINPANEL_API_PORT", "8095") or 8095)
        passed = _wait_for_v2ray_feed_canary_by_id(port, test_subscription_id)
        core.stage_end("v2ray_subscription_smoke", started)
        if not passed:
            return False, ["v2ray_subscription"]
    return True, []


def _lookup_v2ray_canary_token(subscription_id: str) -> str | None:
    """Resolve a test subscription in the currently activated release.

    Never persist or log the private share token: only its numeric record ID
    is configured in the updater's systemd Environment= drop-in.
    """
    if not re.fullmatch(r"[1-9][0-9]{0,9}", subscription_id):
        return None
    current_backend = "/opt/twinpanel/current/backend"
    if current_backend not in sys.path:
        sys.path.insert(0, current_backend)
    from app.database import SessionLocal
    from app.models import Subscription

    with SessionLocal() as db:
        sub = db.get(Subscription, int(subscription_id))
        if sub is None:
            return None
        if str(getattr(sub.status, "value", sub.status) or "").lower() != "active":
            return None
        token = str(sub.share_code or "").strip()
        return token if re.fullmatch(r"[A-Za-z0-9_-]{8,128}", token) else None


def _wait_for_v2ray_feed_canary_by_id(api_port: int, subscription_id: str) -> bool:
    for attempt in range(4):
        try:
            token = _lookup_v2ray_canary_token(subscription_id)
            if token and _v2ray_feed_canary(api_port, token):
                print("UPDATER_V2RAY_SUBSCRIPTION_CANARY_OK", flush=True)
                return True
        except Exception:
            pass
        if attempt < 3:
            time.sleep(2)
    print("UPDATER_V2RAY_SUBSCRIPTION_CANARY_FAILED", file=sys.stderr, flush=True)
    return False


def _v2ray_feed_canary(api_port: int, token: str) -> bool:
    """Require matching, usable public V2Ray feeds after a release switch."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", token):
        return False
    bodies = []
    for endpoint in ("sub", "multi/v2ray"):
        url = f"http://127.0.0.1:{api_port}/v1/connect/{token}/{endpoint}"
        req = urllib.request.Request(url, headers={"User-Agent": "TwinPanel-Update-Canary/1"})
        try:
            with urllib.request.urlopen(req, timeout=6) as response:
                if response.status != 200:
                    return False
                body = response.read(1048577)
            if not body or len(body) > 1048576:
                return False
            decoded = base64.b64decode(body.strip(), validate=True).decode("utf-8")
            if not any(line.strip().startswith("vless://") for line in decoded.splitlines()):
                return False
            bodies.append(decoded.strip())
        except Exception:
            return False
    return len(bodies) == 2 and bodies[0] == bodies[1]


def _wait_for_v2ray_feed_canary(api_port: int, token: str) -> bool:
    for attempt in range(4):
        if _v2ray_feed_canary(api_port, token):
            print("UPDATER_V2RAY_SUBSCRIPTION_CANARY_OK", flush=True)
            return True
        if attempt < 3:
            time.sleep(2)
    print("UPDATER_V2RAY_SUBSCRIPTION_CANARY_FAILED", file=sys.stderr, flush=True)
    return False


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
