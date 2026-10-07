import subprocess
import os
import re
from pathlib import Path


NGINX_DIR="/etc/nginx/sites-available"
NGINX_ENABLED="/etc/nginx/sites-enabled"


def install_certbot():

    packages = [
        "certbot",
        "python3-certbot-nginx"
    ]

    for p in packages:
        subprocess.run(
            [
                "bash",
                "-c",
                f"command -v {p.split('-')[0]} || apt-get update && apt-get install -y {p}"
            ],
            check=False
        )


def _domain_type_key(domain_type, port: int) -> str:
    value = getattr(domain_type, "value", domain_type)

    if value is not None:
        key = str(value).strip().lower()

        if "." in key:
            key = key.split(".")[-1]

        if key in {
            "shop",
            "panel",
            "api",
            "subscription",
        }:
            return key

    return "shop" if int(port) == 3000 else "api"


def _read_proxy_secret() -> str:
    path = os.environ.get(
        "TWINPANEL_MTLS_PROXY_SHARED_SECRET_FILE",
        "/etc/vpnshop/quota-mtls-proxy.secret",
    )

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as handle:
            value = handle.read().strip()
    except OSError:
        value = ""

    if not value:
        value = os.environ.get(
            "TWINPANEL_MTLS_PROXY_SHARED_SECRET",
            "",
        ).strip()

    return value


def _existing_ssl(path: str):
    if not os.path.exists(path):
        return None

    try:
        current = Path(path).read_text(
            encoding="utf-8"
        )
    except OSError:
        return None

    cert = re.search(
        r"^\s*ssl_certificate\s+([^;]+);",
        current,
        re.MULTILINE,
    )

    key = re.search(
        r"^\s*ssl_certificate_key\s+([^;]+);",
        current,
        re.MULTILINE,
    )

    if not cert or not key:
        return None

    names = re.search(
        r"^\s*server_name\s+([^;]+);",
        current,
        re.MULTILINE,
    )

    server_names = (
        names.group(1).strip()
        if names
        else ""
    )

    return {
        "certificate": cert.group(1).strip(),
        "certificate_key": key.group(1).strip(),
        "server_names": server_names,
    }


def _proxy_headers() -> str:
    return """
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
"""


def _service_locations(
    kind: str,
    host: str,
    port: int,
    secure: bool,
) -> str:

    common = _proxy_headers()

    if kind in {"shop", "panel"}:
        return f"""
    location ~ ^/_next/static/.*\\.css$ {{
        proxy_pass http://{host}:{port};
{common}
        proxy_hide_header Cache-Control;
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
    }}

    location ^~ /v1/ {{
        proxy_pass http://127.0.0.1:8095;
{common}
        proxy_connect_timeout 30s;
        proxy_send_timeout 900s;
        proxy_read_timeout 900s;
        proxy_buffering off;
    }}

    location = /health {{
        proxy_pass http://127.0.0.1:8095/health;
{common}
    }}

    location / {{
        proxy_pass http://{host}:{port};
{common}
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_connect_timeout 30s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }}
"""

    if kind == "subscription":
        return f"""
    # TWINPANEL_SUB_DOWNLOADS_V3
    location /downloads/ {{
        alias /opt/twinpanel-downloads/;
        autoindex off;

        add_header X-Content-Type-Options "nosniff" always;
        add_header Cache-Control "public, max-age=86400" always;
    }}

    location / {{
        proxy_pass http://{host}:{port};
{common}
        proxy_connect_timeout 30s;
        proxy_send_timeout 900s;
        proxy_read_timeout 900s;
        proxy_buffering off;
    }}
"""

    # API
    if not secure:
        # Quota identity must never be accepted over plain HTTP.
        quota = """
    location ~ ^/v1/nodes/[0-9]+/quota(?:/|$) {
        return 426;
    }
"""
    else:
        ca_file = os.environ.get(
            "TWINPANEL_MTLS_CA_FILE",
            "/etc/nginx/mtls/twinpanel-quota-ca.crt",
        )

        if not os.path.isfile(ca_file):
            raise RuntimeError(
                "quota_mtls_ca_missing"
            )

        secret = _read_proxy_secret()

        if not secret:
            raise RuntimeError(
                "quota_mtls_proxy_secret_missing"
            )

        # Header value is quoted safely without printing it.
        escaped_secret = (
            secret
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", "")
            .replace("\n", "")
        )

        quota = f"""
    # TWINPANEL_QUOTA_MTLS_V3
    ssl_client_certificate {ca_file};
    ssl_verify_client optional;
    ssl_verify_depth 2;

    location ~ ^/v1/nodes/[0-9]+/quota(?:/|$) {{
        proxy_pass http://{host}:{port};
{common}
        proxy_set_header X-TwinPanel-Proxy-Auth "{escaped_secret}";
        proxy_set_header X-TwinPanel-Client-Cert $ssl_client_escaped_cert;

        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        proxy_buffering off;
    }}
"""

    return f"""
    location /v1/provision/ {{
        proxy_pass http://{host}:{port};
{common}
        proxy_connect_timeout 30s;
        proxy_send_timeout 900s;
        proxy_read_timeout 900s;
        proxy_buffering off;
    }}

{quota}

    location / {{
        proxy_pass http://{host}:{port};
{common}
        proxy_connect_timeout 30s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }}
"""


def create_nginx_config(
    domain: str,
    host: str,
    port: int,
    domain_type=None,
):
    filename = f"{domain}.conf"

    path = os.path.join(
        NGINX_DIR,
        filename,
    )

    enabled = os.path.join(
        NGINX_ENABLED,
        filename,
    )

    kind = _domain_type_key(
        domain_type,
        port,
    )

    ssl = _existing_ssl(path)

    # Preserve aliases only while the same domain config is being rebuilt.
    server_names = domain

    if ssl:
        existing_names = str(
            ssl.get("server_names") or ""
        ).split()

        if domain in existing_names:
            server_names = " ".join(
                existing_names
            )

    if ssl:
        locations = _service_locations(
            kind,
            host,
            port,
            True,
        )

        config = f"""
# TWINPANEL_DOMAIN_MANAGER_V3
server {{
    listen 443 ssl;
    listen [::]:443 ssl;

    server_name {server_names};

{locations}

    ssl_certificate {ssl["certificate"]};
    ssl_certificate_key {ssl["certificate_key"]};
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}}

server {{
    listen 80;
    listen [::]:80;

    server_name {server_names};

    return 301 https://$host$request_uri;
}}
"""
    else:
        locations = _service_locations(
            kind,
            host,
            port,
            False,
        )

        config = f"""
# TWINPANEL_DOMAIN_MANAGER_V3
server {{
    listen 80;
    listen [::]:80;

    server_name {server_names};

{locations}
}}
"""

    old_content = None
    old_mode = None
    enabled_existed = os.path.lexists(
        enabled
    )

    if os.path.exists(path):
        old_content = Path(path).read_text(
            encoding="utf-8"
        )

        old_mode = os.stat(
            path
        ).st_mode & 0o777

    Path(path).write_text(
        config,
        encoding="utf-8",
    )

    # API config contains the proxy shared secret.
    os.chmod(
        path,
        0o600 if kind == "api" else 0o644,
    )

    if not enabled_existed:
        os.symlink(
            path,
            enabled,
        )

    test = subprocess.run(
        ["nginx", "-t"],
        capture_output=True,
        text=True,
    )

    if test.returncode != 0:
        if old_content is None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        else:
            Path(path).write_text(
                old_content,
                encoding="utf-8",
            )

            if old_mode is not None:
                os.chmod(
                    path,
                    old_mode,
                )

        if not enabled_existed:
            try:
                os.unlink(enabled)
            except FileNotFoundError:
                pass

        raise RuntimeError(
            test.stderr.strip()
        )

    subprocess.run(
        [
            "systemctl",
            "reload",
            "nginx",
        ],
        check=True,
    )

    return {
        "ok": True,
        "file": path,
        "domain_type": kind,
        "ssl_preserved": bool(ssl),
    }


def issue_ssl(domain:str):

    install_certbot()


    result = subprocess.run(
        [
            "certbot",
            "--nginx",
            "-d",
            domain,
            "--non-interactive",
            "--agree-tos",
            "-m",
            f"admin@{domain}",
            "--redirect"
        ],
        capture_output=True,
        text=True
    )


    return {
        "ok": result.returncode == 0,
        "output": result.stdout[-2000:],
        "error": result.stderr[-2000:]
    }
