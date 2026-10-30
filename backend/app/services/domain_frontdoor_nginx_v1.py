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


def _write_with_rollback(path: Path, content: str, mode: int) -> tuple[str | None, int | None]:
    old_content = None
    old_mode = None
    if path.exists():
        old_content = path.read_text(encoding="utf-8")
        old_mode = path.stat().st_mode & 0o777
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)
    return old_content, old_mode


def create_nginx_config(
    domain: str,
    host: str,
    port: int,
    domain_type=None,
):
    """Render a domain site without competing with the TCP/443 stream front door.

    Before the front door is enabled, behavior remains compatible with the legacy
    renderer. Once the marker exists, HTTPS virtual hosts bind only to
    127.0.0.1:9443; TCP/443 is owned exclusively by Nginx stream and SNI-routed
    to this internal listener or to ocserv TCP/4443.
    """
    filename = f"{domain}.conf"
    path = Path(NGINX_DIR) / filename
    enabled = Path(NGINX_ENABLED) / filename
    kind = _domain_type_key(domain_type, port)
    cert = _certificate(domain)
    secure = cert is not None
    locations = _service_locations(kind, host, port, secure)
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

    enabled_existed = enabled.exists() or enabled.is_symlink()
    old_content, old_mode = _write_with_rollback(
        path,
        config,
        0o600 if kind == "api" else 0o644,
    )

    if not enabled_existed:
        enabled.symlink_to(path)

    test = subprocess.run(
        ["nginx", "-t"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    if test.returncode != 0:
        if old_content is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        else:
            path.write_text(old_content, encoding="utf-8")
            if old_mode is not None:
                os.chmod(path, old_mode)
        if not enabled_existed:
            try:
                enabled.unlink()
            except FileNotFoundError:
                pass
        raise RuntimeError(test.stderr.strip() or "nginx_config_test_failed")

    reload_result = subprocess.run(
        ["systemctl", "reload", "nginx"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if reload_result.returncode != 0:
        raise RuntimeError(
            (reload_result.stderr or reload_result.stdout or "nginx_reload_failed").strip()
        )

    return {
        "ok": True,
        "file": str(path),
        "domain_type": kind,
        "ssl_preserved": secure,
        "frontdoor": frontdoor_enabled(),
    }
