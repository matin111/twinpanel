from __future__ import annotations

import asyncio
import math
import re
import shlex

from . import transport_policy_v17 as v17
from . import transport_policy_v19 as v19
from . import transport_policy_v20 as v20
from . import tunnel_transport_manager_v7 as v7
from .database import SessionLocal
from .models import Node, Tunnel
from .routers.provision import ssh_connect_saved


KERNEL_GRE = "kernel_gre"
MAX_AUTO_PACKET_LOSS_PCT = 5.0

_BASE_OVERLAY_HEALTH_REMOTE = None


# ============================================================
# TWINPANEL KERNEL GRE ACTIVE ROUTING / AUTO V21
#
# Kernel GRE is an externally managed L3 member, just like TP2027 from the
# selection pipeline's point of view. It owns its own systemd service and /30.
# V21 adds it to the existing V20 quality competition without replacing V20's
# anti-flap, dwell, manual-authority or legacy-fallback logic.
#
# Continuous throughput tests are deliberately NOT run here. Health sampling
# remains bounded to service/interface/L3 loss+RTT; saturation benchmarks stay
# installation/diagnostic work, not a 5-second manager loop.
# ============================================================


def _parse_marker(text: str, key: str) -> str:
    match = re.search(
        rf"^{re.escape(key)}=(.*)$",
        str(text or ""),
        flags=re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def _loss(text: str) -> float | None:
    value = v7.loss_of(str(text or ""))
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _latency(text: str) -> int | None:
    value = v7.latency_from_ping(str(text or ""))
    try:
        return None if value is None else max(0, int(value))
    except (TypeError, ValueError):
        return None


async def _peer_snapshot(
    conn,
    *,
    interface: str,
    local_ip: str,
    peer_ip: str,
    service: str,
) -> dict:
    command = f'''
set +e
SERVICE_STATE="$(systemctl is-active {shlex.quote(service)} 2>/dev/null || true)"

echo "TP_SERVICE_STATE=$SERVICE_STATE"

ip link show dev {shlex.quote(interface)} >/dev/null 2>&1
IFACE_RC=$?
echo "TP_IFACE_RC=$IFACE_RC"

ip -4 addr show dev {shlex.quote(interface)} 2>/dev/null | grep -qw {shlex.quote(local_ip)}
ADDR_RC=$?
echo "TP_ADDR_RC=$ADDR_RC"

PING_OUT="$(ping -I {shlex.quote(interface)} -c 5 -i 0.2 -W 2 {shlex.quote(peer_ip)} 2>&1 || true)"
printf '%s\n' "$PING_OUT"

true
'''

    result = await conn.run(
        command,
        check=False,
        timeout=20,
    )

    text = (result.stdout or "") + "\n" + (result.stderr or "")
    service_state = _parse_marker(text, "TP_SERVICE_STATE")
    iface_rc = _parse_marker(text, "TP_IFACE_RC")
    addr_rc = _parse_marker(text, "TP_ADDR_RC")
    loss = _loss(text)
    latency = _latency(text)

    ok = bool(
        service_state == "active"
        and iface_rc == "0"
        and addr_rc == "0"
        and loss is not None
        and loss <= MAX_AUTO_PACKET_LOSS_PCT
        and latency is not None
    )

    return {
        "ok": ok,
        "service_state": service_state,
        "iface_ok": iface_rc == "0",
        "address_ok": addr_rc == "0",
        "latency_ms": latency,
        "packet_loss_pct": loss,
    }


async def kernel_gre_health_remote(
    tunnel_id: int,
    name: str,
    cfg: dict,
) -> tuple[str, dict]:
    global _BASE_OVERLAY_HEALTH_REMOTE

    normalized = str(name or "").strip().lower()

    if normalized != KERNEL_GRE:
        if _BASE_OVERLAY_HEALTH_REMOTE is None:
            return (
                normalized,
                {
                    "ok": False,
                    "latency_ms": None,
                    "error": "kernel_gre_v21_base_probe_missing",
                },
            )

        return await _BASE_OVERLAY_HEALTH_REMOTE(
            int(tunnel_id),
            normalized,
            cfg,
        )

    cfg = dict(cfg or {})

    required = (
        "interface",
        "iran_ip",
        "exit_ip",
        "iran_service",
        "exit_service",
    )

    missing = [
        key
        for key in required
        if not str(cfg.get(key) or "").strip()
    ]

    if missing:
        return (
            normalized,
            {
                "ok": False,
                "latency_ms": None,
                "packet_loss_pct": None,
                "error": "kernel_gre_config_missing:" + ",".join(missing),
            },
        )

    # The TP27 parity installer accepts peer-L3 as its mode-selection gate, but
    # Auto promotion is intentionally stricter: the installation-time full
    # egress diagnostic must also have succeeded before production Auto may
    # promote this member.
    if cfg.get("full_probe_ok") is not True:
        return (
            normalized,
            {
                "ok": False,
                "latency_ms": None,
                "packet_loss_pct": None,
                "error": "kernel_gre_full_probe_not_ok",
            },
        )

    db = SessionLocal()
    ci = ce = None

    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is None:
            return normalized, {"ok": False, "latency_ms": None, "error": "tunnel_missing"}

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if iran is None or exit_node is None:
            return normalized, {"ok": False, "latency_ms": None, "error": "node_missing"}

        ci, ce = await asyncio.gather(
            ssh_connect_saved(iran, db),
            ssh_connect_saved(exit_node, db),
        )

        interface = str(cfg["interface"]).strip()
        iran_ip = str(cfg["iran_ip"]).strip().split("/", 1)[0]
        exit_ip = str(cfg["exit_ip"]).strip().split("/", 1)[0]

        iran_result, exit_result = await asyncio.gather(
            _peer_snapshot(
                ci,
                interface=interface,
                local_ip=iran_ip,
                peer_ip=exit_ip,
                service=str(cfg["iran_service"]).strip(),
            ),
            _peer_snapshot(
                ce,
                interface=interface,
                local_ip=exit_ip,
                peer_ip=iran_ip,
                service=str(cfg["exit_service"]).strip(),
            ),
        )

        losses = [
            float(item["packet_loss_pct"])
            for item in (iran_result, exit_result)
            if item.get("packet_loss_pct") is not None
        ]

        latencies = [
            int(item["latency_ms"])
            for item in (iran_result, exit_result)
            if item.get("latency_ms") is not None
        ]

        worst_loss = max(losses) if losses else None
        worst_latency = max(latencies) if latencies else None
        ok = bool(iran_result.get("ok") and exit_result.get("ok"))

        if not ok:
            details = []
            if not iran_result.get("ok"):
                details.append("iran=" + repr(iran_result))
            if not exit_result.get("ok"):
                details.append("exit=" + repr(exit_result))

            return (
                normalized,
                {
                    "ok": False,
                    "latency_ms": None,
                    "packet_loss_pct": worst_loss,
                    "error": ("kernel_gre_peer_health_failed:" + " | ".join(details))[:1400],
                    "telemetry_source": "kernel_gre_v21_bidirectional_l3",
                },
            )

        return (
            normalized,
            {
                "ok": True,
                "latency_ms": worst_latency,
                "packet_loss_pct": worst_loss,
                "error": None,
                "telemetry_source": "kernel_gre_v21_bidirectional_l3",
            },
        )

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return (
            normalized,
            {
                "ok": False,
                "latency_ms": None,
                "packet_loss_pct": None,
                "error": ("kernel_gre_probe_exception:" + repr(exc))[:1400],
            },
        )
    finally:
        for conn in (ci, ce):
            if conn is not None:
                try:
                    conn.close()
                    await conn.wait_closed()
                except Exception:
                    pass
        db.close()


def install_kernel_gre_active_v21() -> None:
    """
    Extend the already-installed V20 runtime in place.

    Manual authority, V20 scoring, candidate hold, minimum dwell and failure
    confirmations remain untouched. Only membership + kernel-specific health
    probing are added.
    """
    global _BASE_OVERLAY_HEALTH_REMOTE

    v7.OVERLAY_NAMES.add(KERNEL_GRE)
    v7.SUPPORTED_NAMES.add(KERNEL_GRE)

    v17.AUTO_PRIORITY[KERNEL_GRE] = 50

    modern = frozenset(
        set(v17.MODERN_NAMES)
        | {KERNEL_GRE}
    )

    managed = frozenset(
        set(v17.MANAGED_TRANSPORT_NAMES)
        | {KERNEL_GRE}
    )

    v17.MODERN_NAMES = modern
    v17.MANAGED_TRANSPORT_NAMES = managed

    v19.MODERN_NAMES = modern
    v19.MANAGED_TRANSPORT_NAMES = managed

    v20.MODERN_NAMES = modern
    v20.ALL_NAMES = frozenset(
        set(modern)
        | set(v20.LEGACY_NAMES)
    )

    if _BASE_OVERLAY_HEALTH_REMOTE is None:
        _BASE_OVERLAY_HEALTH_REMOTE = v7.overlay_health_remote

    v7.overlay_health_remote = kernel_gre_health_remote

    # v8 points at this function object; the function reads V17's mutated
    # MANAGED_TRANSPORT_NAMES at call time, so no new manager loop is needed.
    print(
        "TWINPANEL_KERNEL_GRE_ACTIVE_V21 "
        "manual=1 auto=1 desired_state=tpgr/10.248 health=bidirectional_l3",
        flush=True,
    )
