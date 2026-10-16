from __future__ import annotations

import re
import shlex
from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from . import tp2027_provision
from .database import get_db
from .deps import require_admin
from .models import Node, Tunnel, TunnelStatus, TunnelTransport
from .routers import tunnels
from .routers.provision import ssh_connect_saved


# TWINPANEL_TP2027_REAL_EGRESS_V37
#
# Root cause found in production Tunnel #9:
# - TCP 2027 peer L3 was healthy (0% loss, ~164 ms)
# - Exit had IPv4 forwarding enabled and direct Internet access
# - no TP2027 FORWARD or POSTROUTING rules existed
# - public egress through tp27t9 therefore timed out
#
# V37 adds only the missing Exit forwarding/NAT for TP2027 overlay /30s.
# It does not rotate ports, keys, MTU, addresses, binaries, or protocol settings.

_runtime_applied = False
_original_firewall_script = tp2027_provision._firewall_script

_NAMES = (
    "tcp_2027",
    "arq_2027",
    "kcp_2027",
    "quic_2027",
)


def _status(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _extended_firewall_script(tunnel_id: int) -> str:
    tid = int(tunnel_id)
    base = str(_original_firewall_script(tid) or "").rstrip()

    # The historical renderer terminates immediately after opening the carrier
    # listener ports. Remove only that final terminator and append the missing
    # dataplane egress rules before restoring `exit 0`.
    if base.endswith("exit 0"):
        base = base[: -len("exit 0")].rstrip()

    lines = [
        base,
        "",
        "# TwinPanel V37: TP2027 real Exit egress",
        "OUT_IF=\"$(ip -4 route show default | awk '/^default / {print $5; exit}')\"",
        "test -n \"$OUT_IF\" || { echo TP2027_EGRESS_NO_DEFAULT_IF >&2; exit 1; }",
        "sysctl -w net.ipv4.ip_forward=1 >/dev/null",
        "iptables -N TP2027_FWD 2>/dev/null || true",
        "iptables -C FORWARD -j TP2027_FWD 2>/dev/null || iptables -I FORWARD 1 -j TP2027_FWD",
        "",
    ]

    for name in _NAMES:
        runtime = tp2027_provision.tp2027_runtime_values(name, tid)
        iface = shlex.quote(str(runtime["interface"]))
        network = shlex.quote(str(runtime["network"]))
        short = str(runtime["short"])
        marker = f"TP2027-EGRESS-{tid}-{short}"

        lines.extend(
            [
                (
                    "iptables -C TP2027_FWD "
                    f"-i {iface} -s {network} -o \"$OUT_IF\" "
                    f"-m comment --comment {shlex.quote(marker + '-OUT')} -j ACCEPT "
                    "2>/dev/null || iptables -I TP2027_FWD 1 "
                    f"-i {iface} -s {network} -o \"$OUT_IF\" "
                    f"-m comment --comment {shlex.quote(marker + '-OUT')} -j ACCEPT"
                ),
                (
                    "iptables -C TP2027_FWD "
                    f"-i \"$OUT_IF\" -o {iface} -d {network} "
                    "-m conntrack --ctstate ESTABLISHED,RELATED "
                    f"-m comment --comment {shlex.quote(marker + '-RETURN')} -j ACCEPT "
                    "2>/dev/null || iptables -I TP2027_FWD 1 "
                    f"-i \"$OUT_IF\" -o {iface} -d {network} "
                    "-m conntrack --ctstate ESTABLISHED,RELATED "
                    f"-m comment --comment {shlex.quote(marker + '-RETURN')} -j ACCEPT"
                ),
                (
                    "iptables -t nat -C POSTROUTING "
                    f"-s {network} -o \"$OUT_IF\" "
                    f"-m comment --comment {shlex.quote(marker + '-NAT')} -j MASQUERADE "
                    "2>/dev/null || iptables -t nat -I POSTROUTING 1 "
                    f"-s {network} -o \"$OUT_IF\" "
                    f"-m comment --comment {shlex.quote(marker + '-NAT')} -j MASQUERADE"
                ),
                "",
            ]
        )

    lines.extend(
        [
            "echo TP2027_EGRESS_V37_READY out_if=$OUT_IF",
            "exit 0",
            "",
        ]
    )

    return "\n".join(lines)


def _parse_ping(text: str) -> tuple[float | None, int | None]:
    loss = None
    latency = None

    loss_match = re.search(r"([\d.]+)%\s+packet loss", text or "")
    if loss_match:
        try:
            loss = float(loss_match.group(1))
        except Exception:
            loss = None

    latency_match = re.search(r"=\s*[\d.]+/([\d.]+)/", text or "")
    if latency_match:
        try:
            latency = int(round(float(latency_match.group(1))))
        except Exception:
            latency = None

    return loss, latency


async def _verify_transport_on_iran(conn, name: str, tunnel_id: int) -> dict[str, Any]:
    runtime = tp2027_provision.tp2027_runtime_values(name, int(tunnel_id))
    iface = str(runtime["interface"])
    peer = str(runtime["exit_ip"])

    service_result = await conn.run(
        f"systemctl is-active {shlex.quote(str(runtime['iran_service']))}",
        check=False,
        timeout=8,
    )
    iface_result = await conn.run(
        f"ip link show {shlex.quote(iface)} >/dev/null 2>&1",
        check=False,
        timeout=8,
    )

    if service_result.exit_status != 0 or iface_result.exit_status != 0:
        return {
            "transport": name,
            "ok": False,
            "loss_pct": None,
            "latency_ms": None,
            "public_ip": None,
            "error": "service_or_interface_unavailable",
        }

    ping_result = await conn.run(
        f"ping -I {shlex.quote(iface)} -c 5 -W 2 {shlex.quote(peer)}",
        check=False,
        timeout=15,
    )
    ping_text = (ping_result.stdout or "") + "\n" + (ping_result.stderr or "")
    loss, latency = _parse_ping(ping_text)

    curl_result = await conn.run(
        (
            f"curl -4 --interface {shlex.quote(iface)} "
            "--connect-timeout 5 --max-time 12 -fsS https://api.ipify.org"
        ),
        check=False,
        timeout=16,
    )
    public_ip = str(curl_result.stdout or "").strip()

    # A production-selectable member must have real public egress and a clean
    # peer path. A partially responding overlay (for example 60% loss) remains
    # non-selectable even if one request happens to pass.
    ok = bool(
        ping_result.exit_status == 0
        and loss is not None
        and loss <= 20.0
        and curl_result.exit_status == 0
        and public_ip
    )

    error = None
    if not ok:
        if loss is None or loss > 20.0:
            error = f"peer_loss={loss if loss is not None else 'unknown'}"
        elif curl_result.exit_status != 0 or not public_ip:
            detail = str(curl_result.stderr or curl_result.stdout or "egress_failed").strip()
            error = f"public_egress_failed: {detail[-500:]}"
        else:
            error = "real_egress_verification_failed"

    return {
        "transport": name,
        "ok": ok,
        "loss_pct": loss,
        "latency_ms": latency,
        "public_ip": public_ip or None,
        "error": error,
    }


async def repair_tp2027_egress_and_activate(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tid = int(tunnel_id)
    tunnel = db.get(Tunnel, tid)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")

    iran = db.get(Node, int(tunnel.iran_node_id))
    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if iran is None or exit_node is None:
        raise HTTPException(status_code=409, detail="نودهای تونل کامل نیستند")

    iran_conn = None
    exit_conn = None

    try:
        iran_conn, exit_conn = await __import__("asyncio").gather(
            ssh_connect_saved(iran, db),
            ssh_connect_saved(exit_node, db),
        )

        script_path = f"/usr/local/sbin/tp2027-firewall-{tid}-exit"
        script = _extended_firewall_script(tid)
        await tp2027_provision._write_remote_text(
            exit_conn,
            script_path,
            script,
            "0755",
        )

        apply_result = await exit_conn.run(
            shlex.quote(script_path),
            check=False,
            timeout=20,
        )
        if apply_result.exit_status != 0:
            detail = str(apply_result.stderr or apply_result.stdout or "egress_rule_apply_failed")[-1200:]
            raise HTTPException(status_code=502, detail=detail)

        default_result = await exit_conn.run(
            "ip -4 route show default | awk '/^default / {print $5; exit}'",
            check=False,
            timeout=8,
        )
        out_if = str(default_result.stdout or "").strip()

        verification: list[dict[str, Any]] = []
        rows = {
            str(row.transport or "").strip().lower(): row
            for row in db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == tid)
            .all()
        }

        for name in _NAMES:
            row = rows.get(name)
            if row is None or not bool(row.enabled):
                continue

            item = await _verify_transport_on_iran(iran_conn, name, tid)
            verification.append(item)

            row.status = "online" if item["ok"] else "offline"
            row.latency_ms = item.get("latency_ms")
            row.last_error = None if item["ok"] else str(item.get("error") or "real_egress_failed")[:1800]
            if item["ok"]:
                row.last_healthy_at = datetime.utcnow()
            row.updated_at = datetime.utcnow()

        healthy = [item for item in verification if item.get("ok")]
        healthy.sort(
            key=lambda item: (
                float(item.get("loss_pct") or 0.0),
                int(item.get("latency_ms") or 10**9),
                _NAMES.index(str(item.get("transport"))),
            )
        )

        selected = healthy[0] if healthy else None

        if selected is not None:
            selected_name = str(selected["transport"])
            tunnel.mode = "manual"
            tunnel.active_transport = selected_name
            tunnel.preferred_transport = selected_name
            tunnel.status = TunnelStatus.ONLINE
            tunnel.latency_ms = selected.get("latency_ms")
            tunnel.last_switch_at = datetime.utcnow()
        else:
            tunnel.status = TunnelStatus.OFFLINE
            tunnel.latency_ms = None

        db.commit()
        db.refresh(tunnel)

        return {
            "ok": selected is not None,
            "tunnel_id": tid,
            "mode": str(getattr(tunnel, "mode", "") or ""),
            "active_transport": str(tunnel.active_transport or ""),
            "status": _status(tunnel.status),
            "latency_ms": tunnel.latency_ms,
            "exit_interface": out_if or None,
            "selected": selected,
            "verification": verification,
            "safety": {
                "ports_rotated": False,
                "keys_rotated": False,
                "mtu_changed": False,
                "services_restarted": False,
                "database_schema_changed": False,
            },
            "message": (
                f"مسیر واقعی {selected['transport']} با خروج اینترنت تایید و فعال شد"
                if selected is not None
                else "قوانین خروج اعمال شد اما هنوز هیچ TP2027 با خروج اینترنت واقعی تایید نشد"
            ),
            "marker": "TWINPANEL_TP2027_REAL_EGRESS_V37_ACTIVE",
        }

    finally:
        for conn in (iran_conn, exit_conn):
            if conn is not None:
                conn.close()
                await conn.wait_closed()


def apply_tp2027_egress_v37() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    # Future TP2027 install/repair writes the corrected persistent firewall
    # helper. Existing services already call this helper through ExecStartPre.
    tp2027_provision._firewall_script = _extended_firewall_script

    path = "/{tunnel_id}/service-connections/repair-real-egress"
    methods = ("POST",)
    existing = {
        (
            str(getattr(route, "path", "") or ""),
            tuple(sorted(getattr(route, "methods", None) or ())),
        )
        for route in tunnels.router.routes
    }

    key = (path, methods)
    if key not in existing:
        tunnels.router.add_api_route(
            path,
            repair_tp2027_egress_and_activate,
            methods=["POST"],
            dependencies=[Depends(require_admin)],
            summary="Repair TP2027 real Exit egress and activate a verified member",
        )

    _runtime_applied = True

    print(
        "TWINPANEL_TP2027_REAL_EGRESS_V37_ACTIVE "
        "forward=1 nat=1 real_egress_verify=1 manual_verified_pin=1",
        flush=True,
    )
