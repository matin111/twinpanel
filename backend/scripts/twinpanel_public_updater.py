#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
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

FRONTEND_PATHS = (
    'app',
    'components',
    'lib',
    'public',
    'styles',
    'package.json',
    'package-lock.json',
    'tsconfig.json',
    'next-env.d.ts',
    'next.config.js',
    'next.config.mjs',
    'next.config.ts',
    'postcss.config.js',
    'postcss.config.mjs',
    'tailwind.config.js',
    'tailwind.config.ts',
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(**payload):
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps({'updated_at': now(), **payload}, ensure_ascii=False, indent=2), encoding='utf-8')
    os.chmod(tmp, 0o600)
    tmp.replace(STATE)


def read_json(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


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
    out.setdefault('NEXT_TELEMETRY_DISABLED', '1')
    out.setdefault('npm_config_audit', 'false')
    out.setdefault('npm_config_fund', 'false')
    return out


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={'User-Agent': 'TwinPanel-Public-Updater/4'})
    with urllib.request.urlopen(req, timeout=25) as res:
        obj = json.loads(res.read().decode('utf-8'))
    if not isinstance(obj, dict):
        raise RuntimeError('INVALID_MANIFEST')
    return obj


def _version_key(value: str) -> tuple[int, int, int, int, int]:
    raw = str(value or '').strip().lower().lstrip('v')
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:[-.]?([a-z]+)[.-]?(\d*)?)?', raw)
    if not match:
        return (0, 0, 0, -1, 0)
    major, minor, patch = [int(match.group(i) or 0) for i in (1, 2, 3)]
    label = match.group(4) or ''
    number = int(match.group(5) or 0)
    rank = {
        '': 4,
        'stable': 4,
        'release': 4,
        'rc': 3,
        'beta': 2,
        'preview': 1,
        'alpha': 1,
        'dev': 0,
    }.get(label, 0)
    return (major, minor, patch, rank, number)


def resolve_requested_release(requested_version: str, live_version: str) -> tuple[str, bool]:
    """Resolve a queued update against the current stable manifest.

    A newer stable release appearing after the request was queued is safe to
    adopt because the worker still validates installable metadata, repository,
    exact source SHA and the VERSION file before activation. Downgrades or
    unrelated/older manifest changes remain blocked.
    """
    wanted = str(requested_version or '').strip()
    live = str(live_version or '').strip()
    if not wanted or wanted == live:
        return live, False
    if _version_key(live) > _version_key(wanted):
        return live, True
    raise RuntimeError('REQUESTED_RELEASE_CHANGED')


def run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 1200) -> None:
    cp = subprocess.run(args, cwd=str(cwd) if cwd else None, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    if cp.returncode != 0:
        raise RuntimeError(f"COMMAND_FAILED:{' '.join(args)}\n{(cp.stdout or '')[-5000:]}")


def same_file(left: Path, right: Path) -> bool:
    if not left.is_file() or not right.is_file():
        return False
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        return left.read_bytes() == right.read_bytes()
    except OSError:
        return False


def hardlink_tree(source: Path, target: Path) -> bool:
    if not source.is_dir():
        return False
    try:
        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, symlinks=True, copy_function=os.link)
        return True
    except Exception:
        if target.exists() and target.is_dir() and not target.is_symlink():
            shutil.rmtree(target, ignore_errors=True)
        return False


def backup(env: dict[str, str]) -> None:
    python = VENV if VENV.is_file() else Path(sys.executable)
    code = "from app.backup_service import create_backup; print(create_backup(kind='pre_update', send_telegram=False).get('filename',''))"
    run([str(python), '-c', code], cwd=CURRENT / 'backend', env=env, timeout=300)


def restart() -> None:
    subprocess.run(['systemctl', 'daemon-reload'], check=False)
    for unit in ('twinpanel-api.service', 'twinpanel-web.service', 'twinpanel-reseller-bots.service', 'twinpanel-bot.service'):
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


def frontend_changed(repo: Path, previous_sha: str, target_sha: str) -> bool:
    previous = str(previous_sha or '').strip().lower()
    if not previous or previous == target_sha:
        return not bool(previous)
    if len(previous) != 40 or any(ch not in '0123456789abcdef' for ch in previous):
        return True
    try:
        run(['git', '-C', str(repo), 'fetch', '-q', '--depth', '1', 'origin', previous], timeout=300)
        cp = subprocess.run(
            ['git', '-C', str(repo), 'diff', '--quiet', previous, target_sha, '--', *FRONTEND_PATHS],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if cp.returncode == 0:
            return False
        if cp.returncode == 1:
            return True
    except Exception:
        pass
    return True


def normalize_web_permissions(target: Path) -> None:
    for path in (target / '.next', target / 'node_modules'):
        if path.exists():
            subprocess.run(['chown', '-R', 'www-data:www-data', str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    env = runtime_env()
    previous_state = read_json(STATE)
    manifest_url = env.get('TWINPANEL_RELEASE_MANIFEST_URL') or DEFAULT_MANIFEST
    manifest = get_json(manifest_url)
    if manifest.get('installable') is not True or manifest.get('published') is not True:
        raise RuntimeError('RELEASE_NOT_INSTALLABLE')

    version = str(manifest.get('version') or '').strip()
    repository = str(manifest.get('repository_url') or DEFAULT_REPOSITORY).strip()
    source_sha = str(manifest.get('source_sha') or '').strip().lower()
    if not version or not repository.startswith('https://github.com/matin111/twinpanel'):
        raise RuntimeError('RELEASE_METADATA_INCOMPLETE')
    if len(source_sha) != 40 or any(ch not in '0123456789abcdef' for ch in source_sha):
        raise RuntimeError('RELEASE_SOURCE_SHA_INVALID')

    requested = read_json(REQUEST)
    wanted = str(requested.get('requested_version') or '').strip()
    version, retargeted = resolve_requested_release(wanted, version)

    current_version = (CURRENT / 'VERSION').read_text(encoding='utf-8').strip()
    if current_version == version:
        save(state='completed', target_version=version, previous_version=current_version, reason='already_latest', source_sha=source_sha)
        return 0

    previous_source_sha = ''
    if str(previous_state.get('target_version') or '').strip() == current_version:
        candidate = str(previous_state.get('source_sha') or '').strip().lower()
        if len(candidate) == 40 and all(ch in '0123456789abcdef' for ch in candidate):
            previous_source_sha = candidate

    current_release = CURRENT.resolve()
    RELEASES.mkdir(parents=True, exist_ok=True)
    final = RELEASES / version
    save(
        state='fetching',
        current_version=current_version,
        target_version=version,
        requested_version=wanted or version,
        retargeted=retargeted,
        source_sha=source_sha,
    )

    frontend_needs_build = True
    with tempfile.TemporaryDirectory(prefix='twinpanel-public-update-') as name:
        tmp = Path(name)
        source = tmp / 'source'
        clone_release(repository, source_sha, source)
        if (source / 'VERSION').read_text(encoding='utf-8').strip() != version:
            raise RuntimeError('RELEASE_VERSION_MISMATCH')

        frontend_needs_build = frontend_changed(source, previous_source_sha, source_sha)

        save(state='backup', target_version=version, requested_version=wanted or version, retargeted=retargeted)
        backup(env)

        if final.exists():
            shutil.rmtree(final)
        shutil.copytree(source, final, symlinks=True, ignore=shutil.ignore_patterns('.git'))

    save(
        state='building',
        target_version=version,
        requested_version=wanted or version,
        retargeted=retargeted,
        fast_path=True,
        frontend_changed=frontend_needs_build,
    )

    python = VENV if VENV.is_file() else Path(sys.executable)
    requirements_reused = same_file(current_release / 'backend/requirements.txt', final / 'backend/requirements.txt')
    if not requirements_reused:
        run([str(python), '-m', 'pip', 'install', '-r', 'backend/requirements.txt'], cwd=final, env=env, timeout=900)

    node_dependencies_reused = False
    frontend_build_reused = False
    lock_unchanged = same_file(current_release / 'package-lock.json', final / 'package-lock.json')

    if not frontend_needs_build and (current_release / '.next').is_dir() and (current_release / 'node_modules').is_dir():
        node_dependencies_reused = hardlink_tree(current_release / 'node_modules', final / 'node_modules')
        frontend_build_reused = node_dependencies_reused and hardlink_tree(current_release / '.next', final / '.next')
        if not frontend_build_reused:
            if (final / '.next').exists():
                shutil.rmtree(final / '.next', ignore_errors=True)
            frontend_needs_build = True

    if frontend_needs_build:
        if lock_unchanged and (current_release / 'node_modules').is_dir():
            node_dependencies_reused = hardlink_tree(current_release / 'node_modules', final / 'node_modules')

        if not node_dependencies_reused:
            if (final / 'package-lock.json').is_file():
                run(['npm', 'ci', '--include=optional', '--prefer-offline', '--no-audit', '--no-fund'], cwd=final, env=env, timeout=1200)
            else:
                run(['npm', 'install', '--prefer-offline', '--no-audit', '--no-fund'], cwd=final, env=env, timeout=1200)

        current_cache = current_release / '.next/cache'
        if current_cache.is_dir() and not (final / '.next/cache').exists():
            hardlink_tree(current_cache, final / '.next/cache')

        run(['npm', 'run', 'build'], cwd=final, env=env, timeout=1500)

    if not (final / '.next').is_dir() or not (final / 'node_modules').is_dir():
        raise RuntimeError('FRONTEND_ARTIFACTS_MISSING')

    normalize_web_permissions(final)

    previous = atomic_switch(final)
    save(
        state='restarting',
        target_version=version,
        requested_version=wanted or version,
        retargeted=retargeted,
        requirements_reused=requirements_reused,
        node_dependencies_reused=node_dependencies_reused,
        frontend_build_reused=frontend_build_reused,
    )
    restart()

    api_port = int(env.get('TWINPANEL_API_PORT', '8095') or 8095)
    web_port = int(env.get('TWINPANEL_WEB_PORT', '3000') or 3000)
    if not healthy(f'http://127.0.0.1:{api_port}/health') or not healthy(f'http://127.0.0.1:{web_port}/health'):
        save(state='rollback', target_version=version, error='POST_UPDATE_HEALTH_FAILED')
        rollback(previous)
        raise RuntimeError('POST_UPDATE_HEALTH_FAILED')

    save(
        state='completed',
        target_version=version,
        previous_version=current_version,
        requested_version=wanted or version,
        retargeted=retargeted,
        source_sha=source_sha,
        requirements_reused=requirements_reused,
        node_dependencies_reused=node_dependencies_reused,
        frontend_build_reused=frontend_build_reused,
        completed_at=now(),
    )
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
