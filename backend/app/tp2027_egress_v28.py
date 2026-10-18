from __future__ import annotations

import asyncio
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


# Current-line restoration of the previously merged V37 repair. V28 keeps the
# important safety invariant missing from the historical implementation: if no
# TP2027 member verifies, a healthy SSH Relay/SSH TUN/Backhaul/MTunnel logical
# path is preserved instead of being marked offline.
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
    if base.endswith("exit 0"):
        base = base[: -len("exit 0")].rstrip()

    lines = [
        base,
        "",
        "# TwinPanel V28: TP2027 real Exit egress",
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
        marker = f"TP2027-EGRESS-{tid}-{runtime['short']}"

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
            "echo TP2027_EGRESS_V28_READY out_if=$OUT_IF",
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
            pass
    latency_match = re.search(r"=\s*[\d.]+/([\d.]+)/", text or "")
    if latency_match:
        try:
            latency = int(round(float(latency_match.group(1))))
        except Exception:
            pass
    return loss, latency


async def _verify_transport_on_iran(
    conn,
    name: str,
    tunnel_id: int,
) -> dict[str, Any]:
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
            detail = str(
                curl_result.stderr or curl_result.stdout or "egress_failed"
            ).strip()
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

    rows = {
        str(row.transport or "").strip().lower(): row
        for row in (
            db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == tid)
            .all()
        )
    }
    enabled = [name for name in _NAMES if rows.get(name) and rows[name].enabled]
    if not enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "برای این تانل مسیر TP2027 فعالی وجود ندارد؛ مسیر سالم فعلی "
                "بدون تغییر حفظ شد"
            ),
        )

    iran = db.get(Node, int(tunnel.iran_node_id))
    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if iran is None or exit_node is None:
        raise HTTPException(status_code=409, detail="نودهای تونل کامل نیستند")

    # Preserve the aggregate logical path unless a TP2027 candidate is actually
    # verified. This is what protects a working SSH Relay fallback.
    original = {
        "mode": tunnel.mode,
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "status": tunnel.status,
        "latency_ms": tunnel.latency_ms,
        "last_switch_at": tunnel.last_switch_at,
        "is_active": tunnel.is_active,
    }

    iran_conn = None
    exit_conn = None
    try:
        iran_conn, exit_conn = await asyncio.gather(
            ssh_connect_saved(iran, db),
            ssh_connect_saved(exit_node, db),
        )

        script_path = f"/usr/local/sbin/tp2027-firewall-{tid}-exit"
        await tp2027_provision._write_remote_text(
            exit_conn,
            script_path,
            _extended_firewall_script(tid),
            "0755",
        )
        apply_result = await exit_conn.run(
            shlex.quote(script_path),
            check=False,
            timeout=20,
        )
        if apply_result.exit_status != 0:
            detail = str(
                apply_result.stderr
                or apply_result.stdout
                or "egress_rule_apply_failed"
            )[-1200:]
            raise HTTPException(status_code=502, detail=detail)

        default_result = await exit_conn.run(
            "ip -4 route show default | awk '/^default / {print $5; exit}'",
            check=False,
            timeout=8,
        )
        out_if = str(default_result.stdout or "").strip()

        verification: list[dict[str, Any]] = []
        for name in enabled:
            row = rows[name]
            item = await _verify_transport_on_iran(iran_conn, name, tid)
            verification.append(item)
            row.status = "online" if item["ok"] else "offline"
            row.latency_ms = item.get("latency_ms")
            row.last_error = (
                None
                if item["ok"]
                else str(item.get("error") or "real_egress_failed")[:1800]
            )
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
            tunnel.is_active = True
            tunnel.active_transport = selected_name
            tunnel.preferred_transport = selected_name
            tunnel.status = TunnelStatus.ONLINE
            tunnel.latency_ms = selected.get("latency_ms")
            tunnel.last_switch_at = datetime.utcnow()
        else:
            tunnel.mode = original["mode"]
            tunnel.is_active = original["is_active"]
            tunnel.active_transport = original["active_transport"]
            tunnel.preferred_transport = original["preferred_transport"]
            tunnel.status = original["status"]
            tunnel.latency_ms = original["latency_ms"]
            tunnel.last_switch_at = original["last_switch_at"]

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
            "fallback_preserved": selected is None,
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
                else "هیچ TP2027 با خروج واقعی تایید نشد؛ مسیر سالم قبلی بدون تغییر حفظ شد"
            ),
            "marker": "TWINPANEL_TP2027_REAL_EGRESS_V28_ACTIVE",
        }
    finally:
        for conn in (iran_conn, exit_conn):
            if conn is not None:
                conn.close()
                try:
                    await conn.wait_closed()
                except Exception:
                    pass


def apply_tp2027_egress_v28() -> None:
    global _runtime_applied
    if _runtime_applied:
        return

    tp2027_provision._firewall_script = _extended_firewall_script

    path = "/{tunnel_id}/service-connections/repair-real-egress"
    key = (path, ("POST",))
    existing = {
        (
            str(getattr(route, "path", "") or ""),
            tuple(sorted(getattr(route, "methods", None) or ())),
        )
        for route in tunnels.router.routes
    }
    if key in existing:
        raise RuntimeError("TP2027 real-egress route already registered")

    tunnels.router.add_api_route(
        path,
        repair_tp2027_egress_and_activate,
        methods=["POST"],
        dependencies=[Depends(require_admin)],
        summary="Repair TP2027 real Exit egress without degrading fallback",
    )

    _runtime_applied = True
    print(
        "TWINPANEL_TP2027_REAL_EGRESS_V28_ACTIVE "
        "forward=1 nat=1 real_egress_verify=1 fallback_preserved=1",
        flush=True,
    )
