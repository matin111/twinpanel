from __future__ import annotations

import base64
import shlex

from .modern_protocol_runtime import CONFIG_PATH, SERVICE_NAME
from .routers.provision import cmd


SERVICE_UNIT_PATH = f"/etc/systemd/system/{SERVICE_NAME}.service"
SERVICE_UNIT = f"""[Unit]
Description=TwinPanel Modern VPN Core (sing-box)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/twinpanel-sing-box run -c {CONFIG_PATH}
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
"""


async def ensure_singbox_service_unit(conn) -> dict[str, str]:
    """Converge the managed sing-box unit without starting it before config exists."""
    encoded = base64.b64encode(SERVICE_UNIT.encode("utf-8")).decode("ascii")
    target = shlex.quote(SERVICE_UNIT_PATH)
    await cmd(
        conn,
        "set -eu; "
        f"target={target}; "
        'tmp="${target}.new-$$"; '
        f"printf '%s' {shlex.quote(encoded)} | base64 -d > \"$tmp\"; "
        'chmod 644 "$tmp"; '
        'if [ ! -f "$target" ] || ! cmp -s "$tmp" "$target"; then '
        '  mv "$tmp" "$target"; '
        '  systemctl daemon-reload; '
        'else '
        '  rm -f "$tmp"; '
        'fi; '
        f"systemctl enable {SERVICE_NAME}.service >/dev/null",
        timeout=120,
    )
    return {"service": SERVICE_NAME, "unit": SERVICE_UNIT_PATH}


__all__ = [
    "SERVICE_UNIT",
    "SERVICE_UNIT_PATH",
    "ensure_singbox_service_unit",
]
