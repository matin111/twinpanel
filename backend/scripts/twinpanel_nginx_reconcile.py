#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


MARKER = "# TWINPANEL_LONG_REQUESTS_V2"
LEGACY_MARKER = "# TWINPANEL_PROVISION_LONG_REQUEST_V1"
DEFAULT_SITE = Path("/etc/nginx/sites-available/twinpanel")
DEFAULT_BACKUP = Path(
    "/etc/nginx/sites-available/twinpanel.pre-long-requests-v2"
)
DEFAULT_STATE = Path(
    "/var/lib/twinpanel-license/nginx-reconcile.json"
)

LONG_EXACT_PATHS = (
    "/v1/provision/install",
    "/v1/provision/ensure-classic-protocol",
    "/v1/provision/repair-protocols-saved",
)
MODERN_INSTALL_LOCATION = (
    r"location ~ ^/v1/settings/vpn/modern-protocols/[0-9]+/install$ {"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def detect_api_port() -> int:
    values: dict[str, str] = {}
    for path in (
        Path("/etc/twinpanel/install.env"),
        Path("/etc/twinpanel/backend.env"),
        Path("/etc/twinpanel/frontend.env"),
    ):
        values.update(_env_file(path))

    raw = str(
        values.get("TWINPANEL_API_PORT")
        or os.getenv("TWINPANEL_API_PORT")
        or ""
    ).strip()
    if raw.isdigit():
        port = int(raw)
        if 1 <= port <= 65535:
            return port

    backend_url = str(
        values.get("TWINPANEL_BACKEND_URL")
        or os.getenv("TWINPANEL_BACKEND_URL")
        or ""
    ).strip()
    if backend_url:
        try:
            parsed = urlparse(backend_url)
            if parsed.port and 1 <= int(parsed.port) <= 65535:
                return int(parsed.port)
        except (TypeError, ValueError):
            pass

    return 8095


def _proxy_block(location: str, api_port: int, indent: str) -> str:
    child = indent + "  "
    return (
        f"{indent}{location}\n"
        f"{child}proxy_pass http://127.0.0.1:{int(api_port)};\n"
        f"{child}proxy_http_version 1.1;\n"
        f"{child}proxy_set_header Host $host;\n"
        f"{child}proxy_set_header X-Real-IP $remote_addr;\n"
        f"{child}proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        f"{child}proxy_set_header X-Forwarded-Proto $scheme;\n"
        f"{child}proxy_set_header X-Forwarded-Host $host;\n"
        f"{child}proxy_connect_timeout 15s;\n"
        f"{child}proxy_send_timeout 1800s;\n"
        f"{child}proxy_read_timeout 1800s;\n"
        f"{child}send_timeout 1800s;\n"
        f"{indent}}}\n\n"
    )


def _long_request_block(api_port: int, indent: str = "  ") -> str:
    if not 1 <= int(api_port) <= 65535:
        raise RuntimeError("API_PORT_INVALID")
    parts = [
        f"{indent}{MARKER}\n",
        f"{indent}# Keep only bounded package/runtime mutations on the long timeout.\n",
        f"{indent}# Ordinary /v1 reads and fast mutations retain Nginx defaults.\n",
    ]
    for path in LONG_EXACT_PATHS:
        parts.append(_proxy_block(f"location = {path} {{", api_port, indent))
    parts.append(_proxy_block(MODERN_INSTALL_LOCATION, api_port, indent))
    return "".join(parts)


def _legacy_managed_block_valid(content: str) -> bool:
    required = (
        LEGACY_MARKER,
        "location = /v1/provision/install {",
        "proxy_connect_timeout 15s;",
        "proxy_send_timeout 1800s;",
        "proxy_read_timeout 1800s;",
        "send_timeout 1800s;",
    )
    return (
        content.count(LEGACY_MARKER) == 1
        and all(item in content for item in required)
    )


def _managed_block_valid(content: str) -> bool:
    required = [
        MARKER,
        MODERN_INSTALL_LOCATION,
        "proxy_connect_timeout 15s;",
        "proxy_send_timeout 1800s;",
        "proxy_read_timeout 1800s;",
        "send_timeout 1800s;",
    ]
    required.extend(f"location = {path} {{" for path in LONG_EXACT_PATHS)
    return (
        content.count(MARKER) == 1
        and LEGACY_MARKER not in content
        and all(item in content for item in required)
        and content.count("proxy_read_timeout 1800s;") >= 4
    )


def _remove_legacy_block(content: str) -> str:
    if LEGACY_MARKER not in content:
        return content
    if not _legacy_managed_block_valid(content):
        raise RuntimeError("NGINX_PROVISION_BLOCK_INVALID")

    pattern = re.compile(
        r"(?ms)^[ \t]*"
        + re.escape(LEGACY_MARKER)
        + r"\n.*?^[ \t]*}\n\n(?=[ \t]*location[ \t]+/v1/[ \t]*\{)"
    )
    upgraded, count = pattern.subn("", content, count=1)
    if count != 1:
        raise RuntimeError("NGINX_LEGACY_BLOCK_UPGRADE_FAILED")
    return upgraded


def patch_nginx_site_text(content: str, api_port: int) -> str:
    """Converge scoped long-running API routes without rewriting site policy."""
    if MARKER in content:
        if not _managed_block_valid(content):
            raise RuntimeError("NGINX_LONG_REQUEST_BLOCK_INVALID")
        return content

    content = _remove_legacy_block(content)

    generic = re.search(
        r"(?m)^(?P<indent>[ \t]*)location[ \t]+/v1/[ \t]*\{[ \t]*$",
        content,
    )
    if generic is None:
        raise RuntimeError("NGINX_V1_LOCATION_NOT_FOUND")

    block = _long_request_block(api_port, generic.group("indent"))
    patched = content[: generic.start()] + block + content[generic.start() :]
    if not _managed_block_valid(patched):
        raise RuntimeError("NGINX_LONG_REQUEST_BLOCK_RENDER_FAILED")

    generic_index = patched.find("location /v1/ {")
    managed_locations = [
        f"location = {path} {{" for path in LONG_EXACT_PATHS
    ] + [MODERN_INSTALL_LOCATION]
    if generic_index < 0 or any(
        patched.find(location) < 0 or patched.find(location) > generic_index
        for location in managed_locations
    ):
        raise RuntimeError("NGINX_LONG_REQUEST_LOCATION_ORDER_INVALID")
    return patched


def _atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _run(argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )


def _binary(configured: str | None, name: str, fallback: str) -> str:
    value = str(configured or "").strip()
    if value:
        return value
    if Path(fallback).is_file():
        return fallback
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"{name.upper()}_NOT_FOUND")
    return found


def _restore_site(site: Path, previous: str, mode: int) -> None:
    _atomic_write(site, previous, mode)


def reconcile_nginx_site(
    *,
    site: Path,
    api_port: int,
    backup: Path = DEFAULT_BACKUP,
    nginx_bin: str | None = None,
    systemctl: str | None = None,
    reload_nginx: bool = False,
) -> dict[str, object]:
    site = Path(site)
    if not site.is_file():
        return {
            "ok": True,
            "checked_at": _now(),
            "site": str(site),
            "changed": False,
            "skipped": "site_missing",
        }

    previous = site.read_text(encoding="utf-8")
    patched = patch_nginx_site_text(previous, api_port)
    if patched == previous:
        return {
            "ok": True,
            "checked_at": _now(),
            "site": str(site),
            "api_port": int(api_port),
            "changed": False,
            "reloaded": False,
        }

    mode = site.stat().st_mode & 0o777
    if not backup.exists():
        _atomic_write(backup, previous, mode or 0o644)

    _atomic_write(site, patched, mode or 0o644)
    nginx = _binary(nginx_bin, "nginx", "/usr/sbin/nginx")
    validation = _run([nginx, "-t"], timeout=20)
    if validation.returncode != 0:
        _restore_site(site, previous, mode or 0o644)
        raise RuntimeError(
            "NGINX_CONFIG_TEST_FAILED:"
            + (validation.stdout or "")[-800:].replace("\n", " ")
        )

    reloaded = False
    if reload_nginx:
        ctl = _binary(systemctl, "systemctl", "/usr/bin/systemctl")
        reload_result = _run([ctl, "reload", "nginx"], timeout=20)
        if reload_result.returncode != 0:
            _restore_site(site, previous, mode or 0o644)
            restored_validation = _run([nginx, "-t"], timeout=20)
            if restored_validation.returncode == 0:
                _run([ctl, "reload", "nginx"], timeout=20)
            raise RuntimeError(
                "NGINX_RELOAD_FAILED:"
                + (reload_result.stdout or "")[-800:].replace("\n", " ")
            )
        reloaded = True

    return {
        "ok": True,
        "checked_at": _now(),
        "site": str(site),
        "api_port": int(api_port),
        "changed": True,
        "reloaded": reloaded,
        "backup": str(backup),
    }


def _write_state(payload: dict[str, object], state: Path) -> None:
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            state,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            0o600,
        )
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely converge TwinPanel Nginx long-request timeout policy",
    )
    parser.add_argument(
        "--site",
        default=str(os.getenv("TWINPANEL_NGINX_SITE") or DEFAULT_SITE),
    )
    parser.add_argument("--api-port", type=int, default=None)
    parser.add_argument("--backup", default=str(DEFAULT_BACKUP))
    parser.add_argument("--nginx-bin", default=None)
    parser.add_argument("--systemctl", default=None)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--state-file", default=str(DEFAULT_STATE))
    args = parser.parse_args(argv)

    site = Path(args.site)
    state = Path(args.state_file)
    api_port = int(args.api_port or detect_api_port())

    try:
        result = reconcile_nginx_site(
            site=site,
            api_port=api_port,
            backup=Path(args.backup),
            nginx_bin=args.nginx_bin,
            systemctl=args.systemctl,
            reload_nginx=bool(args.reload),
        )
        _write_state(result, state)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        failed = {
            "ok": False,
            "checked_at": _now(),
            "site": str(site),
            "api_port": api_port,
            "error": str(exc)[:1200],
        }
        _write_state(failed, state)
        print(
            json.dumps(failed, ensure_ascii=False, separators=(",", ":")),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
