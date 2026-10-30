from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any


# TWINPANEL_DOMAIN_SSL_RUNTIME_V1
#
# Domain SSL issuance must never install packages inside an HTTP request.
# It also must not let Certbot attempt to take over TCP/443 when another
# production daemon (notably ocserv) already owns that listener.


def _tcp_443_owners() -> list[str]:
    try:
        result = subprocess.run(
            ["ss", "-H", "-lntp", "sport = :443"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    owners: list[str] = []
    for name in re.findall(r'\(\("([^"\s]+)"', result.stdout or ""):
        value = str(name or "").strip()
        if value and value not in owners:
            owners.append(value)
    return owners


def https_port_conflict() -> dict[str, Any] | None:
    owners = _tcp_443_owners()
    blocking = [name for name in owners if name != "nginx"]
    if not blocking:
        return None
    return {
        "code": "https_port_conflict",
        "owners": blocking,
        "message": "TCP/443 is owned by another service",
    }


def issue_ssl(domain: str, *, timeout_seconds: int = 180) -> dict[str, Any]:
    conflict = https_port_conflict()
    if conflict:
        owners = ",".join(conflict["owners"])
        return {
            "ok": False,
            "error": f"https_port_conflict:{owners}",
            "code": "https_port_conflict",
            "owners": conflict["owners"],
        }

    certbot = shutil.which("certbot")
    if not certbot:
        return {
            "ok": False,
            "error": "certbot_not_installed",
            "code": "certbot_not_installed",
        }

    try:
        result = subprocess.run(
            [
                certbot,
                "--nginx",
                "-d",
                domain,
                "--non-interactive",
                "--agree-tos",
                "-m",
                f"admin@{domain}",
                "--redirect",
            ],
            capture_output=True,
            text=True,
            timeout=max(30, int(timeout_seconds)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = str(exc.stdout or "")[-1000:]
        error = str(exc.stderr or "")[-1000:]
        return {
            "ok": False,
            "error": "certbot_timeout",
            "code": "certbot_timeout",
            "output": output,
            "detail": error,
        }
    except OSError as exc:
        return {
            "ok": False,
            "error": f"certbot_exec_failed:{type(exc).__name__}",
            "code": "certbot_exec_failed",
        }

    return {
        "ok": result.returncode == 0,
        "code": "ok" if result.returncode == 0 else "certbot_failed",
        "output": (result.stdout or "")[-2000:],
        "error": (result.stderr or "")[-2000:],
    }
