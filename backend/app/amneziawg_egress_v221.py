from __future__ import annotations

import base64
import shlex
from typing import Any


AMNEZIAWG_SUBNET = "10.254.0.0/16"
AMNEZIAWG_INTERFACE = "tpawg0"
EGRESS_SERVICE = "twinpanel-amneziawg-egress.service"
EGRESS_SCRIPT = "/usr/local/lib/twinpanel/amneziawg-egress"
RULE_COMMENT = "TwinPanel-AmneziaWG-Egress"
EGRESS_CONTRACT = 221


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


async def ensure_amneziawg_egress(conn: Any) -> dict[str, str | int]:
    """Install and activate persistent IPv4 egress for the AmneziaWG pool.

    The rules are independent from status telemetry and are owned by one exact
    comment so repeated provisioning is idempotent and cleanup never touches
    unrelated firewall state.
    """

    helper = f'''#!/bin/sh
set -eu
SUBNET={shlex.quote(AMNEZIAWG_SUBNET)}
IFACE={shlex.quote(AMNEZIAWG_INTERFACE)}
COMMENT={shlex.quote(RULE_COMMENT)}
EGRESS="$(ip -4 route show default | awk 'NR==1 {{print $5}}')"
[ -n "$EGRESS" ]

ipt() {{
    iptables -w 10 "$@"
}}

add_rule() {{
    table="$1"; shift
    if ! ipt -t "$table" -C "$@" 2>/dev/null; then
        ipt -t "$table" -A "$@"
    fi
}}

del_rule() {{
    table="$1"; shift
    while ipt -t "$table" -C "$@" 2>/dev/null; do
        ipt -t "$table" -D "$@"
    done
}}

case "${{1:-up}}" in
  up)
    sysctl -w net.ipv4.ip_forward=1 >/dev/null
    add_rule filter FORWARD -i "$IFACE" -o "$EGRESS" -s "$SUBNET" -m comment --comment "$COMMENT" -j ACCEPT
    add_rule filter FORWARD -i "$EGRESS" -o "$IFACE" -d "$SUBNET" -m conntrack --ctstate RELATED,ESTABLISHED -m comment --comment "$COMMENT" -j ACCEPT
    add_rule nat POSTROUTING -s "$SUBNET" -o "$EGRESS" -m comment --comment "$COMMENT" -j MASQUERADE
    ;;
  down)
    del_rule nat POSTROUTING -s "$SUBNET" -o "$EGRESS" -m comment --comment "$COMMENT" -j MASQUERADE
    del_rule filter FORWARD -i "$EGRESS" -o "$IFACE" -d "$SUBNET" -m conntrack --ctstate RELATED,ESTABLISHED -m comment --comment "$COMMENT" -j ACCEPT
    del_rule filter FORWARD -i "$IFACE" -o "$EGRESS" -s "$SUBNET" -m comment --comment "$COMMENT" -j ACCEPT
    ;;
  *)
    echo "usage: $0 [up|down]" >&2
    exit 64
    ;;
esac
'''

    unit = f'''[Unit]
Description=TwinPanel AmneziaWG managed egress
After=network-online.target twinpanel-amneziawg.service
Wants=network-online.target
Requires=twinpanel-amneziawg.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={EGRESS_SCRIPT} up
ExecStop={EGRESS_SCRIPT} down

[Install]
WantedBy=multi-user.target
'''

    helper64 = _b64(helper)
    unit64 = _b64(unit)
    command = (
        "set -eu; "
        "install -d -m 755 /usr/local/lib/twinpanel; "
        f"printf '%s' {shlex.quote(helper64)} | base64 -d > {shlex.quote(EGRESS_SCRIPT)}; "
        f"chmod 755 {shlex.quote(EGRESS_SCRIPT)}; "
        f"printf '%s' {shlex.quote(unit64)} | base64 -d > /etc/systemd/system/{EGRESS_SERVICE}; "
        "systemctl daemon-reload; "
        f"systemctl enable {EGRESS_SERVICE} >/dev/null; "
        f"systemctl restart {EGRESS_SERVICE}; "
        f"systemctl is-active --quiet {EGRESS_SERVICE}; "
        f"iptables -w 10 -t nat -C POSTROUTING -s {shlex.quote(AMNEZIAWG_SUBNET)} "
        "-o \"$(ip -4 route show default | awk 'NR==1 {print $5}')\" "
        f"-m comment --comment {shlex.quote(RULE_COMMENT)} -j MASQUERADE"
    )
    result = await conn.run(command, check=False)
    if int(result.exit_status or 0) != 0:
        message = str(result.stderr or result.stdout or "amneziawg egress activation failed").strip()
        raise RuntimeError(message)

    return {
        "service": EGRESS_SERVICE,
        "subnet": AMNEZIAWG_SUBNET,
        "interface": AMNEZIAWG_INTERFACE,
        "contract": EGRESS_CONTRACT,
    }


__all__ = [
    "AMNEZIAWG_INTERFACE",
    "AMNEZIAWG_SUBNET",
    "EGRESS_CONTRACT",
    "EGRESS_SERVICE",
    "RULE_COMMENT",
    "ensure_amneziawg_egress",
]
