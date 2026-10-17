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
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/var/lib/twinpanel-license')
REQUEST = ROOT / 'update-request.json'
STATE = ROOT / 'update-state.json'
CURRENT = Path('/opt/twinpanel/current')
RELEASES = Path('/opt/twinpanel/releases')
VENV = Path('/opt/twinpanel/venv/bin/python3')
DEFAULT_MANIFEST = 'https://raw.githubusercontent.com/matin111/twinpanel/main/releases/stable.json'


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(**payload):
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps({'updated_at': now(), **payload}, ensure_ascii=False, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600)
    tmp.replace(STATE)


def env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    p = Path(path)
    if not p.is_file():
        return out
    for raw in p.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def runtime_env() -> dict[str, str]:
    out = dict(os.environ)
    out.update(env_file('/etc/twinpanel/install.env'))
    out.update(env_file('/etc/twinpanel/backend.env'))
    return out


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={'User-Agent': 'TwinPanel-Public-Updater/1'})
    with urllib.request.urlopen(req, timeout=25) as res:
        obj = json.loads(res.read().decode('utf-8'))
    if not isinstance(obj, dict):
        raise RuntimeError('INVALID_MANIFEST')
    return obj


def download(url: str, target: Path) -> None:
    req = urllib.request.Request(url, headers={'User-Agent': 'TwinPanel-Public-Updater/1'})
    with urllib.request.urlopen(req, timeout=120) as res, target.open('wb') as fh:
        shutil.copyfileobj(res, fh, length=1024 * 1024)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 1200) -> None:
    cp = subprocess.run(args, cwd=str(cwd) if cwd else None, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if cp.returncode != 0:
        raise RuntimeError(f"COMMAND_FAILED:{' '.join(args)}\n{(cp.stdout or '')[-5000:]}")


def safe_extract(archive: Path, dest: Path) -> Path:
    dest = dest.resolve()
    with tarfile.open(archive, 'r:gz') as tf:
        for member in tf.getmembers():
            target = (dest / member.name).resolve()
            if target != dest and dest not in target.parents:
                raise RuntimeError('UNSAFE_ARCHIVE')
        tf.extractall(dest)
    if (dest / 'backend').is_dir():
        return dest
    children = [p for p in dest.iterdir() if p.is_dir()]
    if len(children) == 1 and (children[0] / 'backend').is_dir():
        return children[0]
    raise RuntimeError('INVALID_RELEASE_LAYOUT')


def backup(env: dict[str, str]) -> None:
    python = VENV if VENV.is_file() else Path(sys.executable)
    code = "from app.backup_service import create_backup; print(create_backup(kind='pre_update', send_telegram=False).get('filename',''))"
    run([str(python), '-c', code], cwd=CURRENT / 'backend', env=env, timeout=300)


def restart() -> None:
    subprocess.run(['systemctl', 'daemon-reload'], check=False)
    for unit in ('twinpanel-api.service', 'twinpanel-web.service', 'twinpanel-reseller-bots.service'):
        if subprocess.run(['systemctl', 'cat', unit], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            subprocess.run(['systemctl', 'restart', unit], check=False)


def healthy(url: str, seconds: int = 90) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=4) as res:
                if 200 <= res.status < 300:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def atomic_switch(target: Path) -> Path | None:
    previous = CURRENT.resolve() if CURRENT.exists() else None
    if CURRENT.exists() and not CURRENT.is_symlink():
        raise RuntimeError('CURRENT_NOT_SYMLINK')
    tmp = Path('/opt/twinpanel/.current-next')
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(target)
    tmp.replace(CURRENT)
    return previous


def rollback(previous: Path | None) -> None:
    if not previous or not previous.exists():
        return
    tmp = Path('/opt/twinpanel/.current-rollback')
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(previous)
    tmp.replace(CURRENT)
    restart()


def main() -> int:
    env = runtime_env()
    manifest_url = env.get('TWINPANEL_RELEASE_MANIFEST_URL') or DEFAULT_MANIFEST
    manifest = get_json(manifest_url)
    if manifest.get('installable') is not True:
        raise RuntimeError('RELEASE_NOT_INSTALLABLE')

    version = str(manifest.get('version') or '').strip()
    url = str(manifest.get('package_url') or '').strip()
    expected = str(manifest.get('sha256') or '').strip().lower()
    if not version or not url or len(expected) != 64:
        raise RuntimeError('RELEASE_METADATA_INCOMPLETE')

    requested = {}
    try:
        requested = json.loads(REQUEST.read_text(encoding='utf-8')) if REQUEST.is_file() else {}
    except Exception:
        requested = {}
    wanted = str(requested.get('requested_version') or '').strip()
    if wanted and wanted != version:
        raise RuntimeError('REQUESTED_RELEASE_CHANGED')

    current_version = (CURRENT / 'VERSION').read_text(encoding='utf-8').strip()
    if current_version == version:
        save(state='completed', target_version=version, previous_version=current_version, reason='already_latest')
        return 0

    RELEASES.mkdir(parents=True, exist_ok=True)
    final = RELEASES / version
    save(state='downloading', current_version=current_version, target_version=version)

    with tempfile.TemporaryDirectory(prefix='twinpanel-public-update-') as name:
        tmp = Path(name)
        archive = tmp / 'release.tar.gz'
        extracted = tmp / 'release'
        extracted.mkdir()
        download(url, archive)
        if digest(archive) != expected:
            raise RuntimeError('RELEASE_SHA256_MISMATCH')

        save(state='backup', target_version=version)
        backup(env)
        save(state='extracting', target_version=version)
        root = safe_extract(archive, extracted)
        if (root / 'VERSION').read_text(encoding='utf-8').strip() != version:
            raise RuntimeError('RELEASE_VERSION_MISMATCH')
        if final.exists():
            shutil.rmtree(final)
        shutil.copytree(root, final, symlinks=True)

    save(state='building', target_version=version)
    python = VENV if VENV.is_file() else Path(sys.executable)
    run([str(python), '-m', 'pip', 'install', '-r', 'backend/requirements.txt'], cwd=final, env=env, timeout=900)
    if (final / 'package-lock.json').is_file():
        run(['npm', 'ci', '--include=optional'], cwd=final, env=env, timeout=1200)
    else:
        run(['npm', 'install', '--no-audit', '--no-fund'], cwd=final, env=env, timeout=1200)
    run(['npm', 'run', 'build'], cwd=final, env=env, timeout=1500)

    previous = atomic_switch(final)
    save(state='restarting', target_version=version)
    restart()

    api_port = int(env.get('TWINPANEL_API_PORT', '8095') or 8095)
    web_port = int(env.get('TWINPANEL_WEB_PORT', '3000') or 3000)
    if not healthy(f'http://127.0.0.1:{api_port}/health') or not healthy(f'http://127.0.0.1:{web_port}/health'):
        save(state='rollback', target_version=version, error='POST_UPDATE_HEALTH_FAILED')
        rollback(previous)
        raise RuntimeError('POST_UPDATE_HEALTH_FAILED')

    save(state='completed', target_version=version, previous_version=current_version, completed_at=now())
    try:
        REQUEST.unlink()
    except FileNotFoundError:
        pass
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        save(state='failed', error=str(exc)[:1200])
        raise
