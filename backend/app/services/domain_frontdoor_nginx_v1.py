from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .ssl_manager import (
    NGINX_DIR,
    NGINX_ENABLED,
    _domain_type_key,
    _service_locations,
)


# TWINPANEL_DOMAIN_FRONTDOOR_NGINX_V1
FRONTDOOR_MARKER = Path("/etc/twinpanel/domain-frontdoor-v1")
ACME_ROOT = Path("/var/lib/twinpanel/acme")
INTERNAL_HTTPS_LISTEN = "127.0.0.1:9443"
STREAM_MAP_BUILDER = Path("/usr/local/sbin/twinpanel-domain-stream-map")


def frontdoor_enabled() -> bool:
    return FRONTDOOR_MARKER.is_file()


def _certificate(domain: str) -> dict[str, str] | None:
    base = Path("/etc/letsencrypt/live") / domain
    cert = base / "fullchain.pem"
    key = base / "privkey.pem"
    if cert.is_file() and key.is_file():
        return {
            "certificate": str(cert),
            "certificate_key": str(key),
        }
    return None


def _acme_location() -> str:
    return f"""
    # TWINPANEL_ACME_WEBROOT_V1
    location ^~ /.well-known/acme-challenge/ {{
        root {ACME_ROOT};
        default_type text/plain;
        try_files $uri =404;
    }}
"""


def _service_locations_frontdoor(
    kind: str,
    host: str,
    port: int,
    secure: bool,
) -> str:
    try:
        return _service_locations(kind, host, port, secure)
    except RuntimeError as exc:
        # TWINPANEL_API_HTTPS_QUOTA_FAIL_CLOSED_V1
        if (
            kind == "api"
            and secure
            and str(exc) in {
                "quota_mtls_ca_missing",
                "quota_mtls_proxy_secret_missing",
            }
        ):
            return _service_locations(kind, host, port, False)
        raise


def _write_with_rollback(path: Path, content: str, mode: int) -> tuple[str | None, int | None]:
    old_content = None
    old_mode = None
    if path.exists():
        old_content = path.read_text(encoding="utf-8")
        old_mode = path.stat().st_mode & 0o777
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)
    return old_content, old_mode


def _snapshot_enabled_entry(enabled: Path) -> dict[str, object]:
    if enabled.is_symlink():
        return {"kind": "symlink", "target": os.readlink(enabled)}
    if enabled.exists():
        if not enabled.is_file():
            raise RuntimeError("unsupported_enabled_entry_type")
        return {
            "kind": "file",
            "content": enabled.read_text(encoding="utf-8"),
            "mode": enabled.stat().st_mode & 0o777,
        }
    return {"kind": "missing"}


def _ensure_enabled_symlink(path: Path, enabled: Path) -> None:
    if enabled.is_symlink():
        try:
            if enabled.resolve(strict=False) == path.resolve(strict=False):
                return
        except OSError:
            pass
    if os.path.lexists(enabled):
        enabled.unlink()
    enabled.symlink_to(path)


def _restore_enabled_entry(enabled: Path, state: dict[str, object]) -> None:
    if os.path.lexists(enabled):
        enabled.unlink()
    kind = state.get("kind")
    if kind == "missing":
        return
    if kind == "symlink":
        enabled.symlink_to(str(state.get("target") or ""))
        return
    if kind == "file":
        enabled.write_text(str(state.get("content") or ""), encoding="utf-8")
        mode = state.get("mode")
        if isinstance(mode, int):
            os.chmod(enabled, mode)
        return
    raise RuntimeError("unsupported_enabled_snapshot")


def _restore_site(path: Path, old_content: str | None, old_mode: int | None) -> None:
    if old_content is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    else:
        path.write_text(old_content, encoding="utf-8")
        if old_mode is not None:
            os.chmod(path, old_mode)


def refresh_frontdoor_map() -> None:
    if not frontdoor_enabled() or not STREAM_MAP_BUILDER.is_file():
        return
    result = subprocess.run(
        [str(STREAM_MAP_BUILDER)], capture_output=True, text=True, timeout=15, check=False
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "frontdoor_map_refresh_failed").strip())


def _reload_nginx() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["systemctl", "reload", "nginx"], capture_output=True, text=True, timeout=20, check=False
    )


def create_nginx_config(domain: str, host: str, port: int, domain_type=None):
    filename = f"{domain}.conf"
    path = Path(NGINX_DIR) / filename
    enabled = Path(NGINX_ENABLED) / filename
    kind = _domain_type_key(domain_type, port)
    cert = _certificate(domain)
    secure = cert is not None
    locations = _service_locations_frontdoor(kind, host, port, secure)
    acme = _acme_location()

    if secure:
        listen = (
            f"    listen {INTERNAL_HTTPS_LISTEN} ssl;\n"
            if frontdoor_enabled()
            else "    listen 443 ssl;\n    listen [::]:443 ssl;\n"
        )
        config = f"""
# TWINPANEL_DOMAIN_MANAGER_V5
server {{
{listen}
    server_name {domain};

{locations}

    ssl_certificate {cert['certificate']};
    ssl_certificate_key {cert['certificate_key']};
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}}

server {{
    listen 80;
    listen [::]:80;

    server_name {domain};
{acme}
    location / {{
        return 301 https://$host$request_uri;
    }}
}}
"""
    else:
        config = f"""
# TWINPANEL_DOMAIN_MANAGER_V5
server {{
    listen 80;
    listen [::]:80;

    server_name {domain};
{acme}
{locations}
}}
"""

    enabled_state = _snapshot_enabled_entry(enabled)
    old_content, old_mode = _write_with_rollback(
        path, config, 0o600 if kind == "api" else 0o644
    )

    try:
        _ensure_enabled_symlink(path, enabled)
        refresh_frontdoor_map()
        test = subprocess.run(
            ["nginx", "-t"], capture_output=True, text=True, timeout=15, check=False
        )
        if test.returncode != 0:
            raise RuntimeError(test.stderr.strip() or "nginx_config_test_failed")
        reload_result = _reload_nginx()
        if reload_result.returncode != 0:
            raise RuntimeError(
                (reload_result.stderr or reload_result.stdout or "nginx_reload_failed").strip()
            )
    except Exception:
        _restore_site(path, old_content, old_mode)
        _restore_enabled_entry(enabled, enabled_state)
        try:
            refresh_frontdoor_map()
            rollback_test = subprocess.run(
                ["nginx", "-t"], capture_output=True, text=True, timeout=15, check=False
            )
            if rollback_test.returncode == 0:
                _reload_nginx()
        except Exception:
            pass
        raise

    return {
        "ok": True,
        "file": str(path),
        "domain_type": kind,
        "ssl_preserved": secure,
        "frontdoor": frontdoor_enabled(),
    }
