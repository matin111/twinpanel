#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
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
DEFAULT_REPOSITORY = 'https://github.com/matin111/twinpanel.git'
ARTIFACT_FORMAT = 'twinpanel-prebuilt-v1'
ALLOWED_ARTIFACT_PREFIX = 'https://github.com/matin111/twinpanel/releases/download/'
STARTED_MONOTONIC = time.monotonic()
STAGE_SECONDS: dict[str, float] = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def elapsed_seconds() -> float:
    return round(max(0.0, time.monotonic() - STARTED_MONOTONIC), 3)


def stage_begin() -> float:
    return time.monotonic()


def stage_end(name: str, started: float) -> None:
    STAGE_SECONDS[name] = round(max(0.0, time.monotonic() - started), 3)


def save(**payload) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(
        json.dumps(
            {
                'updated_at': now(),
                'elapsed_seconds': elapsed_seconds(),
                'stage_seconds': dict(STAGE_SECONDS),
                **payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
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
    out.update(env_file('/etc/twinpanel/frontend.env'))
    out.setdefault('NEXT_TELEMETRY_DISABLED', '1')
    out.setdefault('npm_config_audit', 'false')
    out.setdefault('npm_config_fund', 'false')
    return out


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={'User-Agent': 'TwinPanel-Public-Updater/6'})
    with urllib.request.urlopen(req, timeout=20) as res:
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
    wanted = str(requested_version or '').strip()
    live = str(live_version or '').strip()
    if not wanted or wanted == live:
        return live, False
    if _version_key(live) > _version_key(wanted):
        return live, True
    raise RuntimeError('REQUESTED_RELEASE_CHANGED')


def run(
    args: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 1200,
) -> None:
    cp = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if cp.returncode != 0:
        raise RuntimeError(
            f"COMMAND_FAILED:{' '.join(args)}\n{(cp.stdout or '')[-5000:]}"
        )


def same_file(left: Path, right: Path) -> bool:
    if not left.is_file() or not right.is_file():
        return False
    try:
        return left.stat().st_size == right.stat().st_size and left.read_bytes() == right.read_bytes()
    except OSError:
        return False


def backup(env: dict[str, str]) -> None:
    python = VENV if VENV.is_file() else Path(sys.executable)
    code = (
        "from app.backup_service import create_backup; "
        "print(create_backup(kind='pre_update', send_telegram=False).get('filename',''))"
    )
    run(
        [str(python), '-c', code],
        cwd=CURRENT / 'backend',
        env=env,
        timeout=300,
    )


def existing_units() -> list[str]:
    units: list[str] = []
    for unit in (
        'twinpanel-api.service',
        'twinpanel-web.service',
        'twinpanel-reseller-bots.service',
        'twinpanel-bot.service',
    ):
        if subprocess.run(
            ['systemctl', 'cat', unit],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).returncode == 0:
            units.append(unit)
    return units


def restart_services() -> None:
    subprocess.run(
        ['systemctl', 'daemon-reload'],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
    units = existing_units()
    if units:
        subprocess.run(
            ['systemctl', '--no-block', 'restart', *units],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )


def health_ok(url: str, expected_version: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'TwinPanel-Update-Health/3'})
        with urllib.request.urlopen(req, timeout=2) as res:
            if not (200 <= res.status < 300):
                return False
            payload = json.loads(res.read().decode('utf-8'))
        return (
            isinstance(payload, dict)
            and payload.get('ok') is True
            and str(payload.get('version') or '').strip() == expected_version
        )
    except Exception:
        return False


def wait_for_healthy(
    urls: dict[str, str],
    expected_version: str,
    seconds: int = 45,
) -> tuple[bool, list[str]]:
    pending = set(urls)
    end = time.time() + seconds
    while pending and time.time() < end:
        for name in tuple(pending):
            if health_ok(urls[name], expected_version):
                pending.remove(name)
        if pending:
            time.sleep(0.5)
    return not pending, sorted(pending)


def healthy_version(url: str, expected_version: str, seconds: int = 45) -> bool:
    ok, _ = wait_for_healthy({'service': url}, expected_version, seconds=seconds)
    return ok


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
    restart_services()


def clone_release(repository: str, source_sha: str, target: Path) -> None:
    run(['git', 'init', '-q', str(target)], timeout=60)
    run(['git', '-C', str(target), 'remote', 'add', 'origin', repository], timeout=60)
    run(
        [
            'git', '-C', str(target), '-c', 'advice.detachedHead=false',
            'fetch', '-q', '--depth', '1', 'origin', source_sha,
        ],
        timeout=300,
    )
    run(['git', '-C', str(target), 'checkout', '-q', '--detach', 'FETCH_HEAD'], timeout=60)
    cp = subprocess.run(
        ['git', '-C', str(target), 'rev-parse', 'HEAD'],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=15,
    )
    actual = (cp.stdout or '').strip().lower()
    if cp.returncode != 0 or actual != source_sha:
        raise RuntimeError('SOURCE_COMMIT_VERIFICATION_FAILED')


def artifact_metadata(manifest: dict) -> dict:
    value = manifest.get('artifact')
    return value if isinstance(value, dict) else {}


def validate_artifact_metadata(artifact: dict) -> tuple[str, str, int | None]:
    if str(artifact.get('format') or '').strip() != ARTIFACT_FORMAT:
        raise RuntimeError('RELEASE_ARTIFACT_FORMAT_INVALID')
    arch = str(artifact.get('arch') or 'x86_64').strip().lower()
    machine = platform.machine().strip().lower()
    aliases = {'amd64': 'x86_64', 'x86_64': 'x86_64'}
    if aliases.get(machine, machine) != aliases.get(arch, arch):
        raise RuntimeError('RELEASE_ARTIFACT_ARCH_MISMATCH')
    url = str(artifact.get('url') or '').strip()
    digest = str(artifact.get('sha256') or '').strip().lower()
    if not url.startswith(ALLOWED_ARTIFACT_PREFIX):
        raise RuntimeError('RELEASE_ARTIFACT_URL_INVALID')
    if len(digest) != 64 or any(ch not in '0123456789abcdef' for ch in digest):
        raise RuntimeError('RELEASE_ARTIFACT_SHA256_INVALID')
    size = artifact.get('size_bytes')
    try:
        size_value = int(size) if size is not None else None
    except Exception:
        size_value = None
    if size_value is not None and size_value <= 0:
        size_value = None
    return url, digest, size_value


def download_verified_artifact(
    url: str,
    expected_sha256: str,
    destination: Path,
    expected_size: int | None = None,
) -> int:
    req = urllib.request.Request(url, headers={'User-Agent': 'TwinPanel-Public-Updater/6'})
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(req, timeout=60) as response, destination.open('wb') as out:
        while True:
            chunk = response.read(2 * 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 1024 * 1024 * 1024:
                raise RuntimeError('RELEASE_ARTIFACT_TOO_LARGE')
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest().lower() != expected_sha256:
        raise RuntimeError('RELEASE_ARTIFACT_SHA256_MISMATCH')
    if expected_size is not None and total != expected_size:
        raise RuntimeError('RELEASE_ARTIFACT_SIZE_MISMATCH')
    return total


def extract_prebuilt(
    archive: Path,
    destination: Path,
    version: str,
    source_sha: str,
) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode='r:gz') as bundle:
        bundle.extractall(destination, filter='data')
    root = destination / 'twinpanel'
    if not root.is_dir():
        raise RuntimeError('RELEASE_ARTIFACT_ROOT_MISSING')
    if (root / 'VERSION').read_text(encoding='utf-8').strip() != version:
        raise RuntimeError('RELEASE_ARTIFACT_VERSION_MISMATCH')
    meta = read_json(root / '.twinpanel-release.json')
    if str(meta.get('format') or '') != ARTIFACT_FORMAT:
        raise RuntimeError('RELEASE_ARTIFACT_METADATA_INVALID')
    if str(meta.get('version') or '').strip() != version:
        raise RuntimeError('RELEASE_ARTIFACT_METADATA_VERSION_MISMATCH')
    if str(meta.get('source_sha') or '').strip().lower() != source_sha:
        raise RuntimeError('RELEASE_ARTIFACT_SOURCE_SHA_MISMATCH')
    if not (root / '.next/standalone/server.js').is_file():
        raise RuntimeError('RELEASE_STANDALONE_FRONTEND_MISSING')
    if not (root / 'backend/app/main.py').is_file():
        raise RuntimeError('RELEASE_BACKEND_MISSING')
    return root


def prepare_source_fallback(
    repository: str,
    source_sha: str,
    version: str,
    destination: Path,
    env: dict[str, str],
) -> Path:
    source = destination / 'source'
    clone_release(repository, source_sha, source)
    if (source / 'VERSION').read_text(encoding='utf-8').strip() != version:
        raise RuntimeError('RELEASE_VERSION_MISMATCH')
    if (source / 'package-lock.json').is_file():
        run(
            ['npm', 'ci', '--include=optional', '--prefer-offline', '--no-audit', '--no-fund'],
            cwd=source,
            env=env,
            timeout=1200,
        )
    else:
        run(
            ['npm', 'install', '--prefer-offline', '--no-audit', '--no-fund'],
            cwd=source,
            env=env,
            timeout=1200,
        )
    run(['npm', 'run', 'build'], cwd=source, env=env, timeout=1500)
    if not (source / '.next/standalone/server.js').is_file():
        raise RuntimeError('FRONTEND_STANDALONE_BUILD_FAILED')
    git_dir = source / '.git'
    if git_dir.exists():
        shutil.rmtree(git_dir)
    return source


def install_web_unit(release: Path, web_port: int) -> None:
    template = release / 'deploy/systemd/twinpanel-web.service.tpl'
    if not template.is_file():
        raise RuntimeError('WEB_SERVICE_TEMPLATE_MISSING')
    content = template.read_text(encoding='utf-8').replace('__WEB_PORT__', str(web_port))
    path = Path('/etc/systemd/system/twinpanel-web.service')
    tmp = path.with_suffix('.service.tmp')
    tmp.write_text(content, encoding='utf-8')
    os.chmod(tmp, 0o644)
    tmp.replace(path)


def ensure_web_entry_access(target: Path) -> None:
    paths = (target, target / '.next', target / '.next/standalone')
    for path in paths:
        mode = path.stat().st_mode & 0o777
        os.chmod(path, mode | 0o055)
    server = target / '.next/standalone/server.js'
    mode = server.stat().st_mode & 0o777
    os.chmod(server, mode | 0o044)
    check = subprocess.run(
        ['runuser', '-u', 'www-data', '--', 'test', '-r', str(server)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    if check.returncode != 0:
        raise RuntimeError('FRONTEND_ARTIFACT_PERMISSION_INVALID')


def verify_activation(final: Path, version: str) -> None:
    try:
        active = CURRENT.resolve(strict=True)
        target = final.resolve(strict=True)
    except Exception as exc:
        raise RuntimeError('ACTIVATION_PATH_UNRESOLVED') from exc
    if active != target:
        raise RuntimeError('ACTIVATION_PATH_MISMATCH')
    if (CURRENT / 'VERSION').read_text(encoding='utf-8').strip() != version:
        raise RuntimeError('ACTIVATION_VERSION_MISMATCH')


def main() -> int:
    env = runtime_env()

    started = stage_begin()
    manifest_url = env.get('TWINPANEL_RELEASE_MANIFEST_URL') or DEFAULT_MANIFEST
    manifest = get_json(manifest_url)
    stage_end('manifest', started)
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
        save(
            state='completed',
            target_version=version,
            previous_version=current_version,
            reason='already_latest',
            source_sha=source_sha,
        )
        return 0

    current_release = CURRENT.resolve()
    RELEASES.mkdir(parents=True, exist_ok=True)
    final = RELEASES / version
    artifact = artifact_metadata(manifest)
    prebuilt = bool(artifact)
    download_bytes = 0

    save(
        state='fetching',
        current_version=current_version,
        target_version=version,
        requested_version=wanted or version,
        retargeted=retargeted,
        source_sha=source_sha,
        delivery='prebuilt' if prebuilt else 'source-build-fallback',
    )

    with tempfile.TemporaryDirectory(prefix='.twinpanel-update-', dir=RELEASES) as name:
        work = Path(name)
        if prebuilt:
            url, sha256, size_bytes = validate_artifact_metadata(artifact)
            archive = work / 'release.tar.gz'

            save(
                state='downloading',
                target_version=version,
                delivery='prebuilt',
            )
            started = stage_begin()
            download_bytes = download_verified_artifact(
                url,
                sha256,
                archive,
                expected_size=size_bytes,
            )
            stage_end('download', started)

            save(
                state='extracting',
                target_version=version,
                delivery='prebuilt',
                download_bytes=download_bytes,
            )
            started = stage_begin()
            prepared = extract_prebuilt(
                archive,
                work / 'stage',
                version,
                source_sha,
            )
            stage_end('extract', started)
        else:
            started = stage_begin()
            prepared = prepare_source_fallback(
                repository,
                source_sha,
                version,
                work,
                env,
            )
            stage_end('source_build_fallback', started)

        save(
            state='backup',
            target_version=version,
            requested_version=wanted or version,
            retargeted=retargeted,
            delivery='prebuilt' if prebuilt else 'source-build-fallback',
            download_bytes=download_bytes,
        )
        started = stage_begin()
        backup(env)
        stage_end('backup', started)

        started = stage_begin()
        if final.exists():
            shutil.rmtree(final)
        prepared.replace(final)
        stage_end('activate_files', started)

    python = VENV if VENV.is_file() else Path(sys.executable)
    requirements_reused = same_file(
        current_release / 'backend/requirements.txt',
        final / 'backend/requirements.txt',
    )
    if not requirements_reused:
        save(
            state='python-dependencies',
            target_version=version,
            delivery='prebuilt' if prebuilt else 'source-build-fallback',
        )
        started = stage_begin()
        run(
            [str(python), '-m', 'pip', 'install', '-r', 'backend/requirements.txt'],
            cwd=final,
            env=env,
            timeout=900,
        )
        stage_end('python_dependencies', started)

    if not (final / '.next/standalone/server.js').is_file():
        raise RuntimeError('FRONTEND_ARTIFACTS_MISSING')

    started = stage_begin()
    ensure_web_entry_access(final)
    web_port = int(env.get('TWINPANEL_WEB_PORT', '3000') or 3000)
    api_port = int(env.get('TWINPANEL_API_PORT', '8095') or 8095)
    install_web_unit(final, web_port)
    stage_end('runtime_prepare', started)

    previous = atomic_switch(final)
    try:
        verify_activation(final, version)
        save(
            state='restarting',
            target_version=version,
            requested_version=wanted or version,
            retargeted=retargeted,
            delivery='prebuilt' if prebuilt else 'source-build-fallback',
            download_bytes=download_bytes,
            requirements_reused=requirements_reused,
        )

        started = stage_begin()
        restart_services()
        stage_end('restart_dispatch', started)

        verify_activation(final, version)
        started = stage_begin()
        health_ok_all, pending = wait_for_healthy(
            {
                'api': f'http://127.0.0.1:{api_port}/health',
                'web': f'http://127.0.0.1:{web_port}/health',
            },
            version,
            seconds=45,
        )
        stage_end('health', started)
        verify_activation(final, version)
        if not health_ok_all:
            raise RuntimeError('POST_UPDATE_HEALTH_VERSION_FAILED:' + ','.join(pending))
    except Exception:
        save(
            state='rollback',
            target_version=version,
            previous_version=current_version,
            error='ACTIVATION_OR_HEALTH_FAILED',
        )
        rollback(previous)
        raise

    save(
        state='completed',
        target_version=version,
        previous_version=current_version,
        requested_version=wanted or version,
        retargeted=retargeted,
        source_sha=source_sha,
        delivery='prebuilt' if prebuilt else 'source-build-fallback',
        download_bytes=download_bytes,
        requirements_reused=requirements_reused,
        active_path=str(CURRENT.resolve()),
        active_version=(CURRENT / 'VERSION').read_text(encoding='utf-8').strip(),
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
