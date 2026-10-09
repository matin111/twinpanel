from __future__ import annotations

import base64
import shlex


# TWINPANEL_BACKHAUL_ROUTE_GUARDIAN_V1
#
# Backhaul can recreate its TUN device inside the same long-running process.
# Linux removes routes bound to the deleted interface, while systemd does not
# run ExecStartPost again because the service PID never restarted. This
# guardian continuously verifies the source-policy route and recreates it
# whenever the Backhaul interface/address returns.


def backhaul_guardian_values(tunnel_id: int) -> dict:
    tid = int(tunnel_id)
    slot = 10 + (tid % 230)
    table = 24000 + tid

    return {
        "tunnel_id": tid,
        "interface": f"bh{tid}",
        "source_ip": f"10.253.{slot}.1",
        "peer_ip": f"10.253.{slot}.2",
        "table": table,
        "priority": table,
        "service": f"twinpanel-backhaul-route-guardian-{tid}.service",
        "script": f"/usr/local/sbin/tp-backhaul-route-guardian-{tid}",
    }


async def _run(conn, command: str, *, check: bool = True, timeout: int = 120):
    result = await conn.run(
        command,
        check=False,
        timeout=timeout,
    )

    if check and result.exit_status != 0:
        raise RuntimeError(
            (result.stderr or result.stdout or "remote command failed")[-3000:]
        )

    return result


async def _write(conn, path: str, content: str, mode: str):
    payload = base64.b64encode(content.encode()).decode()

    await _run(
        conn,
        f"""
set -e
printf '%s' {shlex.quote(payload)} | base64 -d > {shlex.quote(path)}
chmod {shlex.quote(mode)} {shlex.quote(path)}
""",
    )


async def install_backhaul_route_guardian(tunnel, iran, db) -> dict:
    from .routers.provision import ssh_connect_saved

    values = backhaul_guardian_values(
        int(tunnel.id)
    )

    iface = values["interface"]
    source_ip = values["source_ip"]
    table = int(values["table"])
    priority = int(values["priority"])
    service = values["service"]
    script_path = values["script"]

    script = f'''#!/bin/bash
set -u

IFACE={shlex.quote(iface)}
SRC={shlex.quote(source_ip)}
TABLE={table}
PRIO={priority}
SLEEP_SECONDS=1

log() {{
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}}

ensure_rule() {{
    local current

    current="$(ip -4 rule show priority "$PRIO" 2>/dev/null || true)"

    if [ -n "$current" ] && ! printf '%s\n' "$current" | grep -Fq "from $SRC lookup $TABLE"; then
        log "RULE_PRIORITY_COLLISION priority=$PRIO current=$current"
        return 1
    fi

    if ! printf '%s\n' "$current" | grep -Fq "from $SRC lookup $TABLE"; then
        ip -4 rule add priority "$PRIO" from "$SRC/32" lookup "$TABLE"
        log "RULE_REPAIRED priority=$PRIO source=$SRC table=$TABLE"
    fi

    return 0
}}

ensure_route() {{
    if ! ip -4 route show table "$TABLE" 2>/dev/null | grep -Eq "^default dev $IFACE([[:space:]]|$)"; then
        ip -4 route replace \
            default \
            dev "$IFACE" \
            scope link \
            src "$SRC" \
            table "$TABLE"

        ip -4 route flush cache 2>/dev/null || true

        log "ROUTE_REPAIRED interface=$IFACE source=$SRC table=$TABLE"
    fi
}}

log "GUARDIAN_START interface=$IFACE source=$SRC table=$TABLE priority=$PRIO"

while true; do
    if ip link show "$IFACE" >/dev/null 2>&1 \
       && ip -4 addr show dev "$IFACE" 2>/dev/null | grep -Fq "inet $SRC/"; then

        if ensure_rule; then
            ensure_route || true
        fi
    fi

    sleep "$SLEEP_SECONDS"
done
'''

    unit = f'''[Unit]
Description=TwinPanel Backhaul Route Guardian {int(tunnel.id)}
After=network-online.target twinpanel-backhaul-{int(tunnel.id)}.service
Wants=network-online.target twinpanel-backhaul-{int(tunnel.id)}.service

[Service]
Type=simple
ExecStart={script_path}
Restart=always
RestartSec=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''

    conn = await ssh_connect_saved(
        iran,
        db,
    )

    try:
        await _write(
            conn,
            script_path,
            script,
            "0755",
        )

        await _write(
            conn,
            f"/etc/systemd/system/{service}",
            unit,
            "0644",
        )

        result = await _run(
            conn,
            f"""
set -e
systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}

for i in $(seq 1 15); do
    if systemctl is-active --quiet {shlex.quote(service)} \
       && ip -4 rule show priority {priority} | grep -Fq 'from {source_ip} lookup {table}' \
       && ip -4 route show table {table} | grep -Eq '^default dev {iface}([[:space:]]|$)'; then
        exit 0
    fi
    sleep 1
done

systemctl status {shlex.quote(service)} --no-pager -l || true
journalctl -u {shlex.quote(service)} -n 80 --no-pager || true
exit 70
""",
            check=False,
            timeout=30,
        )

        if result.exit_status != 0:
            raise RuntimeError(
                (result.stderr or result.stdout or "guardian failed")[-3000:]
            )

        return {
            "ok": True,
            **values,
        }

    finally:
        conn.close()
        await conn.wait_closed()
