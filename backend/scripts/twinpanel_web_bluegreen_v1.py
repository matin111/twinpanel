#!/usr/bin/env python3
"""Reversible Next.js 3000->standby->3000 update handoff.

This helper is OPT-IN only. Default invocation is a non-mutating preflight.
It never changes an API route, customer data, network tunnel or subscription.

Lifecycle for a future updater (only when specifically enabled and tested):
    --stage --release /opt/twinpanel/releases/<version> --version <version>
    --route-standby
    [updater restarts the canonical web service on 3000]
    --restore --version <version>        # only after 3000 health is verified

No automatic activation is installed here. The updater, which owns atomic
release activation and rollback, is responsible for using these phases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

MAIN_PORT = 3000
STANDBY_PORT = 33001
STANDBY_UNIT = "twinpanel-web-bluegreen-standby-v1.service"
ROOT = Path("/etc/nginx")
STATE = Path("/var/lib/twinpanel-license/web-bluegreen-v1-state.json")
BACKUP_ROOT = Path("/var/lib/twinpanel-license/web-bluegreen-v1")
RELEASE_ROOT = Path("/opt/twinpanel/releases")
NEEDLE = "proxy_pass http://127.0.0.1:{port};"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(*command: str, timeout: int = 20) -> None:
    subprocess.run(list(command), check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=timeout)


def _require_root() -> None:
    if os.geteuid() != 0:
        raise RuntimeError("WEB_BLUEGREEN_ROOT_REQUIRED")


def _rewrite_site(content: str, previous: int, target: int) -> tuple[str, int]:
    old = NEEDLE.format(port=previous)
    new = NEEDLE.format(port=target)
    if old not in content or new in content:
        raise RuntimeError("WEB_BLUEGREEN_SITE_UNEXPECTED_UPSTREAM")
    return content.replace(old, new), content.count(old)


def _sites() -> list[Path]:
    """Only enabled Nginx files, resolving symlinks without changing links."""
    found: dict[str, Path] = {}
    for root in (ROOT / "sites-enabled", ROOT / "conf.d"):
        if not root.is_dir():
            continue
        for name in sorted(root.iterdir()):
            if not name.is_file():
                continue
            target = name.resolve(strict=True)
            if not target.is_relative_to(ROOT.resolve()):
                raise RuntimeError("WEB_BLUEGREEN_SITE_OUTSIDE_NGINX_ROOT")
            if any(p in name.name for p in (".bak", "~", ".disabled")):
                continue
            found[str(target)] = target
    return list(found.values())


def plan(active_port: int = MAIN_PORT, standby_port: int = STANDBY_PORT) -> dict:
    """Fail closed if any enabled site already uses the standby port."""
    originals: dict[str, str] = {}
    replacements: dict[str, str] = {}
    total = 0
    for path in _sites():
        value = path.read_text(encoding="utf-8")
        marker = NEEDLE.format(port=active_port)
        other = NEEDLE.format(port=standby_port)
        if other in value:
            raise RuntimeError("WEB_BLUEGREEN_ALREADY_SWITCHED_OR_CONFLICT")
        if marker not in value:
            continue
        changed, count = _rewrite_site(value, active_port, standby_port)
        originals[str(path)] = value
        replacements[str(path)] = changed
        total += count
    if not originals or total < 1:
        raise RuntimeError("WEB_BLUEGREEN_NO_ENABLED_SITE_UPSTREAM")
    return {"originals": originals, "replacements": replacements,
            "sites": len(originals), "routes": total}


def _http_health(port: int, version: str, *, seconds: float = 22.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{int(port)}/health", timeout=1.5
            ) as response:
                payload = json.loads(response.read(8192).decode("utf-8"))
            if payload.get("ok") is True and payload.get("version") == version:
                return True
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            pass
        time.sleep(0.3)
    return False


def _save_json(payload: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, STATE)


def _state() -> dict:
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError("WEB_BLUEGREEN_NO_STAGED_RELEASE") from exc
    if not isinstance(value, dict):
        raise RuntimeError("WEB_BLUEGREEN_STATE_CORRUPTED")
    return value


def _write_atomic(path: Path, value: bytes) -> None:
    previous = path.stat()
    descriptor, filename = tempfile.mkstemp(prefix=".web-bluegreen-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(filename, previous.st_mode & 0o777)
        os.chown(filename, previous.st_uid, previous.st_gid)
        os.replace(filename, path)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)


def _validate_release(release: Path, version: str) -> Path:
    actual = release.resolve(strict=True)
    if not actual.is_relative_to(RELEASE_ROOT.resolve()):
        raise RuntimeError("WEB_BLUEGREEN_RELEASE_OUTSIDE_PINNED_ROOT")
    if (actual / "VERSION").read_text(encoding="utf-8").strip() != version:
        raise RuntimeError("WEB_BLUEGREEN_RELEASE_VERSION_MISMATCH")
    work = actual / ".next" / "standalone"
    if not (work / "server.js").is_file():
        raise RuntimeError("WEB_BLUEGREEN_STANDALONE_MISSING")
    return work


def stage(release: Path, version: str) -> dict:
    _require_root()
    if STATE.exists():
        raise RuntimeError("WEB_BLUEGREEN_ALREADY_STAGED")
    before = plan()
    working = _validate_release(release, version)
    # Staging must never change the already active frontend on 3000.
    if subprocess.run(
        ["systemctl", "is-active", "--quiet", STANDBY_UNIT],
        check=False, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=5
    ).returncode == 0:
        raise RuntimeError("WEB_BLUEGREEN_STANDBY_SERVICE_ALREADY_ACTIVE")
    if not _http_health(MAIN_PORT, (Path("/opt/twinpanel/current") / "VERSION").read_text().strip(),
                        seconds=3):
        raise RuntimeError("WEB_BLUEGREEN_PRIMARY_UNHEALTHY")
    _run(
        "systemd-run", "--quiet", "--collect",
        "--unit=" + STANDBY_UNIT.removesuffix(".service"),
        "--property=User=www-data", "--property=Group=www-data",
        "--property=WorkingDirectory=" + str(working),
        "--property=EnvironmentFile=/etc/twinpanel/frontend.env",
        "--property=NoNewPrivileges=yes", "--property=ProtectSystem=full",
        "/usr/bin/env", "HOSTNAME=127.0.0.1",
        "PORT=" + str(STANDBY_PORT), "NODE_ENV=production",
        "/usr/bin/node", str(working / "server.js"),
    )
    if not _http_health(STANDBY_PORT, version):
        _run("systemctl", "stop", STANDBY_UNIT)
        raise RuntimeError("WEB_BLUEGREEN_STANDBY_HEALTH_FAILED")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=False)
    os.chmod(BACKUP_ROOT, 0o700)
    # Persist original configs with checksums so a crash can be recovered.
    manifest: dict[str, dict] = {}
    for index, (path, source) in enumerate(before["originals"].items()):
        basename = f"site-{index:03}.bak"
        backup = BACKUP_ROOT / basename
        backup.write_bytes(source.encode("utf-8"))
        os.chmod(backup, 0o600)
        manifest[path] = {"backup": basename, "before": _sha(source.encode()),
                          "staged": _sha(before["replacements"][path].encode())}
    _save_json({"phase": "staged", "version": version, "sites": manifest,
                "standby_port": STANDBY_PORT, "primary_port": MAIN_PORT})
    return {"staged": True, "version": version, "sites": len(manifest),
            "routes": before["routes"]}


def _switch_files(state: dict, *, to_standby: bool) -> None:
    manifest = state["sites"]
    desired: list[tuple[Path, bytes]] = []
    for path, meta in manifest.items():
        target = Path(path).resolve(strict=True)
        if not target.is_relative_to(ROOT.resolve()):
            raise RuntimeError("WEB_BLUEGREEN_CONFIG_PATH_INVALID")
        original = (BACKUP_ROOT / meta["backup"]).read_bytes()
        if _sha(original) != meta["before"]:
            raise RuntimeError("WEB_BLUEGREEN_BACKUP_HASH_MISMATCH")
        staged_text, _ = _rewrite_site(
            original.decode("utf-8"), MAIN_PORT, STANDBY_PORT,
        )
        staged_bytes = staged_text.encode("utf-8")
        if _sha(staged_bytes) != meta["staged"]:
            raise RuntimeError("WEB_BLUEGREEN_STAGED_HASH_MISMATCH")
        existing = target.read_bytes()
        allowed = {_sha(original), _sha(staged_bytes)}
        if _sha(existing) not in allowed:
            raise RuntimeError("WEB_BLUEGREEN_CONFIG_CHANGED_EXTERNALLY")
        desired.append((target, staged_bytes if to_standby else original))
    # Apply atomically per site, test all at once, and restore on failure.
    previous = {target: target.read_bytes() for target, _ in desired}
    try:
        for target, data in desired:
            _write_atomic(target, data)
        _run("nginx", "-t")
        _run("systemctl", "reload", "nginx")
    except Exception:
        for target, data in previous.items():
            _write_atomic(target, data)
        _run("nginx", "-t")
        _run("systemctl", "reload", "nginx")
        raise


def route_standby() -> dict:
    _require_root()
    state = _state()
    if state["phase"] != "staged":
        raise RuntimeError("WEB_BLUEGREEN_WRONG_STAGE")
    if not _http_health(STANDBY_PORT, state["version"], seconds=3):
        raise RuntimeError("WEB_BLUEGREEN_STANDBY_NOT_READY")
    _switch_files(state, to_standby=True)
    state["phase"] = "serving_standby"
    _save_json(state)
    return {"serving_standby": True, "version": state["version"]}


def restore(version: str) -> dict:
    _require_root()
    state = _state()
    if state["phase"] not in {"serving_standby", "staged"}:
        raise RuntimeError("WEB_BLUEGREEN_WRONG_RESTORE_STATE")
    # Only return traffic to a verified healthy primary instance.
    if not _http_health(MAIN_PORT, version, seconds=6):
        raise RuntimeError("WEB_BLUEGREEN_PRIMARY_NOT_READY_KEEP_STANDBY")
    if state["phase"] == "serving_standby":
        _switch_files(state, to_standby=False)
    _run("systemctl", "stop", STANDBY_UNIT)
    shutil.rmtree(BACKUP_ROOT)
    STATE.unlink(missing_ok=True)
    return {"restored": True, "version": version}


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stage", action="store_true")
    mode.add_argument("--route-standby", action="store_true")
    mode.add_argument("--restore", action="store_true")
    parser.add_argument("--release", type=Path)
    parser.add_argument("--version")
    parser.add_argument("--confirm-controlled-cutover", action="store_true")
    args = parser.parse_args()
    if not (args.stage or args.route_standby or args.restore):
        result = plan()
        print(json.dumps({"mode": "read-only", "sites": result["sites"],
                          "routes": result["routes"]}, separators=(",", ":")))
        return
    if not args.confirm_controlled_cutover:
        raise SystemExit("WEB_BLUEGREEN_CONFIRMATION_REQUIRED")
    if args.stage:
        if args.release is None or not args.version:
            raise SystemExit("WEB_BLUEGREEN_RELEASE_AND_VERSION_REQUIRED")
        result = stage(args.release, args.version)
    elif args.route_standby:
        result = route_standby()
    else:
        if not args.version:
            raise SystemExit("WEB_BLUEGREEN_RESTORE_VERSION_REQUIRED")
        result = restore(args.version)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
