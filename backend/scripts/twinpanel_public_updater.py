#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
DEFAULT_REPOSITORY = 'https://github.com/matin111/twinpanel.git'


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
    req = urllib.request.Request(url, headers={'User-Agent': 'TwinPanel-Public-Updater/2'})
    with urllib.request.urlopen(req, timeout=25) as res:
        obj = json.loads(res.read().decode('utf-8'))
    if not isinstance(obj, dict):
        raise RuntimeError('INVALID_MANIFEST')
    return obj


def run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 1200) -> None:
    cp = subprocess.run(args, cwd=str(cwd) if cwd else None, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if cp.returncode != 0:
        raise RuntimeError(f"COMMAND_FAILED:{' '.join(args)}\n{(cp.stdout or '')[-5000:]}")


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


def clone_release(repository: str, source_sha: str, target: Path) -> None:
    run(['git', 'init', '-q', str(target)], timeout=60)
    run(['git', '-C', str(target), 'remote', 'add', 'origin', repository], timeout=60)
    run(['git', '-C', str(target), '-c', 'advice.detachedHead=false', 'fetch', '-q', '--depth', '1', 'origin', source_sha], timeout=300)
    run(['git', '-C', str(target), 'checkout', '-q', '--detach', 'FETCH_HEAD'], timeout=60)
    cp = subprocess.run(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    actual = (cp.stdout or '').strip()
    if cp.returncode != 0 or actual != source_sha:
        raise RuntimeError('SOURCE_COMMIT_VERIFICATION_FAILED')


def main() -> int:
    env = runtime_env()
    manifest_url = env.get('TWINPANEL_RELEASE_MANIFEST_URL') or DEFAULT_MANIFEST
    manifest = get_json(manifest_url)
    if manifest.get('installable') is not True:
        raise RuntimeError('RELEASE_NOT_INSTALLABLE')

    version = str(manifest.get('version') or '').strip()
    repository = str(manifest.get('repository_url') or DEFAULT_REPOSITORY).strip()
    source_sha = str(manifest.get('source_sha') or '').strip().lower()
    if not version or not repository.startswith('https://github.com/matin111/twinpanel'):
        raise RuntimeError('RELEASE_METADATA_INCOMPLETE')
    if len(source_sha) != 40 or any(ch not in '0123456789abcdef' for ch in source_sha):
        raise RuntimeError('RELEASE_SOURCE_SHA_INVALID')

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
    save(state='fetching', current_version=current_version, target_version=version, source_sha=source_sha)

    with tempfile.TemporaryDirectory(prefix='twinpanel-public-update-') as name:
        tmp = Path(name)
        source = tmp / 'source'
        clone_release(repository, source_sha, source)
        if (source / 'VERSION').read_text(encoding='utf-8').strip() != version:
            raise RuntimeError('RELEASE_VERSION_MISMATCH')

        save(state='backup', target_version=version)
        backup(env)

        if final.exists():
            shutil.rmtree(final)
        shutil.copytree(source, final, symlinks=True, ignore=shutil.ignore_patterns('.git'))

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

    save(state='completed', target_version=version, previous_version=current_version, source_sha=source_sha, completed_at=now())
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
