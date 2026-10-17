#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/var/lib/twinpanel-license")
STATE_FILE = ROOT / "state.json"
REQUEST_FILE = ROOT / "update-request.json"
UPDATE_STATE_FILE = ROOT / "update-state.json"
INSTALLATION_ID_FILE = Path("/etc/twinpanel/installation-id")
CURRENT = Path("/opt/twinpanel/current")
RELEASES = Path("/opt/twinpanel/releases")
VENV_PYTHON = Path("/opt/twinpanel/venv/bin/python3")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_state(**values: Any) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": now_iso(), **values}
    tmp = UPDATE_STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(UPDATE_STATE_FILE)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def load_runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    for path in (
        Path("/etc/twinpanel/install.env"),
        Path("/etc/twinpanel/backend.env"),
    ):
        env.update(read_env(path))
    return env


def vendor_post(base: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base.rstrip("/") + endpoint,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "TwinPanel-Updater/1"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not isinstance(body, dict):
        raise RuntimeError("INVALID_RELEASE_RESPONSE")
    return body


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "TwinPanel-Updater/1"})
    with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if destination != target and destination not in target.parents:
                raise RuntimeError("UNSAFE_RELEASE_ARCHIVE")
        tar.extractall(destination)


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 900) -> None:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        tail = (result.stdout or "")[-6000:]
        raise RuntimeError(f"COMMAND_FAILED:{' '.join(command)}\n{tail}")


def service_exists(name: str) -> bool:
    result = subprocess.run(
        ["systemctl", "cat", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def restart_runtime() -> None:
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    for service in (
        "twinpanel-api.service",
        "twinpanel-preview.service",
        "twinpanel-web.service",
        "twinpanel-bot.service",
        "twinpanel-reseller-bots.service",
    ):
        if service_exists(service):
            subprocess.run(["systemctl", "restart", service], check=False)


def wait_http(url: str, timeout_seconds: int = 90) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "TwinPanel-Updater/1"})
            with urllib.request.urlopen(request, timeout=4) as response:
                if 200 <= int(response.status) < 300:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def create_pre_update_backup(env: dict[str, str]) -> None:
    python = VENV_PYTHON if VENV_PYTHON.is_file() else Path(sys.executable)
    backend = CURRENT / "backend"
    code = (
        "from app.backup_service import create_backup; "
        "result=create_backup(kind='pre_update', send_telegram=False); "
        "print(result.get('filename',''))"
    )
    run([str(python), "-c", code], cwd=backend, env=env, timeout=300)


def normalize_release_root(extracted: Path) -> Path:
    if (extracted / "backend").is_dir() and (extracted / "package.json").is_file():
        return extracted
    children = [p for p in extracted.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / "backend").is_dir() and (children[0] / "package.json").is_file():
        return children[0]
    raise RuntimeError("INVALID_RELEASE_LAYOUT")


def install_dependencies(release: Path, env: dict[str, str]) -> None:
    python = VENV_PYTHON if VENV_PYTHON.is_file() else Path(sys.executable)
    run([str(python), "-m", "pip", "install", "-r", "backend/requirements.txt"], cwd=release, env=env, timeout=900)
    if (release / "package-lock.json").is_file():
        run(["npm", "ci", "--include=optional"], cwd=release, env=env, timeout=1200)
    else:
        run(["npm", "install", "--no-audit", "--no-fund"], cwd=release, env=env, timeout=1200)
    run(["npm", "run", "build"], cwd=release, env=env, timeout=1500)


def switch_current(release: Path) -> Path:
    if CURRENT.exists() and not CURRENT.is_symlink():
        raise RuntimeError("CURRENT_PATH_NOT_SYMLINK")
    previous = CURRENT.resolve() if CURRENT.exists() else Path("")
    temp_link = Path("/opt/twinpanel/.current-next")
    if temp_link.exists() or temp_link.is_symlink():
        temp_link.unlink()
    temp_link.symlink_to(release)
    temp_link.replace(CURRENT)
    return previous


def rollback(previous: Path) -> None:
    if not previous or not previous.exists():
        return
    temp_link = Path("/opt/twinpanel/.current-rollback")
    if temp_link.exists() or temp_link.is_symlink():
        temp_link.unlink()
    temp_link.symlink_to(previous)
    temp_link.replace(CURRENT)
    restart_runtime()


def prune_releases(active: Path, keep: int = 3) -> None:
    entries = [p for p in RELEASES.iterdir() if p.is_dir()]
    entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    survivors = {active.resolve()}
    for item in entries[:keep]:
        survivors.add(item.resolve())
    for item in entries[keep:]:
        try:
            if item.resolve() not in survivors:
                shutil.rmtree(item)
        except Exception:
            pass


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    RELEASES.mkdir(parents=True, exist_ok=True)
    os.chmod(ROOT, 0o700)

    env = load_runtime_env()
    vendor = str(env.get("TWINPANEL_LICENSE_API_URL", "")).strip()
    if not vendor:
        write_state(state="failed", error="LICENSE_API_NOT_CONFIGURED")
        return 2

    license_state = read_json(STATE_FILE)
    request_state = read_json(REQUEST_FILE)
    installation_id = INSTALLATION_ID_FILE.read_text(encoding="utf-8").strip() if INSTALLATION_ID_FILE.is_file() else ""
    entitlement = str(license_state.get("signed_entitlement") or "").strip()
    if not installation_id or not entitlement:
        write_state(state="failed", error="LICENSE_STATE_INCOMPLETE")
        return 3

    current_version = "0.0.0"
    try:
        current_version = (CURRENT / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        pass

    write_state(state="resolving", current_version=current_version)

    try:
        release = vendor_post(
            vendor,
            "/v1/license/release",
            {
                "installation_id": installation_id,
                "signed_entitlement": entitlement,
                "current_version": current_version,
                "requested_version": request_state.get("requested_version"),
                "channel": request_state.get("channel") or license_state.get("release_channel") or "stable",
            },
        )

        version = str(release.get("version") or "").strip()
        package_url = str(release.get("package_url") or "").strip()
        expected_sha = str(release.get("sha256") or "").strip().lower()
        if not version or not package_url or not re_full_sha(expected_sha):
            raise RuntimeError("RELEASE_METADATA_INCOMPLETE")

        final_dir = RELEASES / version
        if final_dir.exists():
            shutil.rmtree(final_dir)

        with tempfile.TemporaryDirectory(prefix="twinpanel-update-") as tmp_name:
            tmp = Path(tmp_name)
            archive = tmp / "release.tar.gz"
            extracted = tmp / "extracted"
            extracted.mkdir()

            write_state(state="downloading", target_version=version)
            download(package_url, archive)
            actual_sha = sha256(archive)
            if actual_sha != expected_sha:
                raise RuntimeError("RELEASE_SHA256_MISMATCH")

            write_state(state="backup", target_version=version)
            create_pre_update_backup(env)

            write_state(state="extracting", target_version=version)
            safe_extract(archive, extracted)
            root = normalize_release_root(extracted)
            shutil.copytree(root, final_dir, symlinks=True)

        write_state(state="building", target_version=version)
        install_dependencies(final_dir, env)

        previous = switch_current(final_dir)
        write_state(state="restarting", target_version=version)
        restart_runtime()

        api_port = int(env.get("TWINPANEL_API_PORT", "8095") or 8095)
        web_port = int(env.get("TWINPANEL_WEB_PORT", "3000") or 3000)
        api_ok = wait_http(f"http://127.0.0.1:{api_port}/health", 90)
        web_ok = wait_http(f"http://127.0.0.1:{web_port}/health", 90)

        if not (api_ok and web_ok):
            write_state(state="rollback", target_version=version, error="POST_UPDATE_HEALTH_FAILED")
            rollback(previous)
            raise RuntimeError("POST_UPDATE_HEALTH_FAILED")

        prune_releases(final_dir)
        write_state(
            state="completed",
            target_version=version,
            previous_version=current_version,
            completed_at=now_iso(),
        )
        try:
            REQUEST_FILE.unlink()
        except FileNotFoundError:
            pass
        return 0

    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        write_state(state="failed", error=f"RELEASE_SERVER_ERROR:{type(exc).__name__}")
        return 10
    except Exception as exc:
        write_state(state="failed", error=str(exc)[:1200])
        return 11


def re_full_sha(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


if __name__ == "__main__":
    raise SystemExit(main())
