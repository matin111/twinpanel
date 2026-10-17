from __future__ import annotations

import asyncio
from datetime import datetime

from . import managed_ops
from . import tp2027_provision
from .routers import tunnel_managed
from .tp2027_multi_exit_v18 import (
    MODERN_NAMES,
    install_tp2027_overlays_v18,
)


# ============================================================
# TWINPANEL MODERN MANAGED RUNTIME V18
#
# Goal: one Iran node may own many simultaneous Exit tunnels without requiring
# one licensed Backhaul carrier process per Exit. Modern TP2027 members are
# provisioned directly over the public underlay and remain the selectable
# primary/failover paths. Legacy transports stay available only when explicitly
# installed; SSH Relay remains the automatic last-resort fallback.
# ============================================================


MODERN_SELECTION_ORDER = (
    "kcp_2027",
    "arq_2027",
    "quic_2027",
    "tcp_2027",
    "backhaul",
    "mtunnel",
    "ssh_tun",
    "ssh_relay",
)

MODERN_EXPECTED_ORDER = (
    "kcp_2027",
    "arq_2027",
    "quic_2027",
    "tcp_2027",
    "ssh_relay",
)

_ORIGINAL_CREATE_RELAY_JOB = tunnel_managed._run_relay_job
_ORIGINAL_REPAIR_RELAY_JOB = managed_ops._repair_relay_job


async def _skip_pre_overlay_relay(
    tunnel_id: int,
) -> tuple[str, object | None, str | None, bool]:
    # Create-managed historically attempted Relay before TP2027 whenever no
    # direct base transport was online. V18 has no required base carrier, so
    # Relay is deferred until all modern direct transports have failed.
    return "ssh_relay", None, None, False


async def _install_tp2027_phase_v18(
    db,
    tunnel_id: int,
    base_online: set[str],
) -> tuple[list[str], dict[str, str], dict[str, object]]:
    del base_online

    installed: list[str] = []
    errors: dict[str, str] = {}
    results: dict[str, object] = {}

    try:
        overlay = await asyncio.wait_for(
            install_tp2027_overlays_v18(int(tunnel_id), db),
            timeout=240,
        )
    except Exception as exc:
        message = str(exc)[:1800]
        for name in MODERN_NAMES:
            errors[name] = message
        overlay = {"transports": {}}

    results["tp2027"] = overlay

    for name, item in (overlay.get("transports") or {}).items():
        if bool(item.get("ok")):
            installed.append(name)
        else:
            errors[name] = str(
                item.get("error") or "TP2027 public-direct install failed"
            )[:1800]

    if installed:
        return installed, errors, results

    # All modern paths failed: only now try the existing independent Relay.
    name, relay_result, relay_error, relay_online = await _ORIGINAL_CREATE_RELAY_JOB(
        int(tunnel_id)
    )
    if relay_result is not None:
        results[name] = relay_result
    if relay_online:
        installed.append(name)
    elif relay_error:
        errors[name] = relay_error

    return installed, errors, results


def diagnose_managed_tunnel_v18(tunnel_id: int, db) -> dict:
    tunnel = db.get(managed_ops.Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    rows = managed_ops._rows(db, tunnel_id)
    modern_online = any(
        managed_ops._row_online(rows.get(name))
        for name in MODERN_NAMES
    )
    relay_online = managed_ops._row_online(rows.get("ssh_relay"))
    backhaul_online = managed_ops._row_online(rows.get("backhaul"))

    selectable_online = [
        name
        for name in (*MODERN_NAMES, "backhaul", "mtunnel", "ssh_tun", "ssh_relay")
        if managed_ops._row_online(rows.get(name))
    ]

    repair_needed: list[str] = []
    transports: list[dict] = []

    for name in MODERN_EXPECTED_ORDER:
        row = rows.get(name)
        enabled = bool(row.enabled) if row else False
        status = managed_ops._status(row.status) if row else "missing"
        issue_code: str | None = None

        if name == "ssh_relay":
            if relay_online:
                issue_code = None
            elif modern_online:
                issue_code = "standby"
            else:
                issue_code = "relay_required"
        elif row is None:
            issue_code = "not_installed"
        elif not enabled:
            issue_code = "disabled"
        elif status != "online":
            issue_code = "unhealthy"

        if issue_code and issue_code != "standby":
            repair_needed.append(name)

        transports.append(
            {
                "transport": name,
                "priority": getattr(row, "priority", None)
                if row is not None
                else (managed_ops.RELAY_PRIORITY if name == "ssh_relay" else None),
                "enabled": enabled,
                "status": "standby"
                if name == "ssh_relay" and issue_code == "standby"
                else status,
                "latency_ms": getattr(row, "latency_ms", None),
                "last_error": getattr(row, "last_error", None),
                "issue_code": issue_code,
                "dependency": None,
            }
        )

    operational = bool(selectable_online)
    return {
        "ok": True,
        "tunnel_id": int(tunnel.id),
        "mode": str(getattr(tunnel, "mode", "auto") or "auto"),
        "status": managed_ops._status(getattr(tunnel, "status", "offline")),
        "active_transport": getattr(tunnel, "active_transport", None),
        "preferred_transport": getattr(tunnel, "preferred_transport", None),
        "backhaul_online": backhaul_online,
        "direct_online": modern_online,
        "modern_online": modern_online,
        "relay_online": relay_online,
        "relay_required": not modern_online,
        "selectable_online": selectable_online,
        "repair_needed": repair_needed,
        "operational": operational,
        "healthy": operational,
        "complete": all(
            managed_ops._row_online(rows.get(name))
            for name in MODERN_NAMES
        ),
        "transports": transports,
        "underlay": "public_direct",
        "multi_exit_safe": True,
    }


async def _repair_managed_tunnel_locked_v18(tunnel_id: int, db) -> dict:
    tunnel = db.get(managed_ops.Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    tunnel.mode = "auto"
    tunnel.is_active = True
    db.commit()

    before = diagnose_managed_tunnel_v18(int(tunnel_id), db)
    need = set(before.get("repair_needed") or [])
    errors: dict[str, str] = {}
    overlay_result = None
    relay_result = None

    overlay_needed = any(name in need for name in MODERN_NAMES)
    if overlay_needed:
        try:
            overlay_result = await asyncio.wait_for(
                install_tp2027_overlays_v18(int(tunnel_id), db),
                timeout=260,
            )
        except Exception as exc:
            db.rollback()
            message = str(exc)[:1800]
            for name in MODERN_NAMES:
                errors[name] = message

    await asyncio.sleep(6)
    db.expire_all()
    middle = diagnose_managed_tunnel_v18(int(tunnel_id), db)

    if not bool(middle.get("modern_online")):
        name, relay_ok, relay_error, relay_result = await _ORIGINAL_REPAIR_RELAY_JOB(
            int(tunnel_id)
        )
        if not relay_ok and relay_error:
            errors[name] = relay_error

    await asyncio.sleep(4)
    db.expire_all()
    after = diagnose_managed_tunnel_v18(int(tunnel_id), db)
    errors = managed_ops._merge_unresolved_errors(after, errors)

    operational = bool(after.get("operational"))
    partial = bool(operational and not after.get("complete"))

    return {
        "ok": operational,
        "healthy": operational,
        "operational": operational,
        "complete": bool(after.get("complete")),
        "partial": partial,
        "tunnel_id": int(tunnel_id),
        "mode": "auto",
        "provisioning_mode": "public_direct_multi_exit_v18",
        "before": before,
        "after": after,
        "base_results": {},
        "ssh_relay_result": relay_result,
        "tp2027_result": overlay_result,
        "errors": errors,
        "remaining": list(after.get("repair_needed") or []),
        "attempted": bool(overlay_needed or not middle.get("modern_online")),
        "repaired_at": datetime.utcnow().isoformat() + "Z",
    }


def apply_modern_runtime_v18() -> None:
    tp2027_provision.TP2027_PRIORITY.clear()
    tp2027_provision.TP2027_PRIORITY.update(
        {
            "kcp_2027": 10,
            "arq_2027": 20,
            "quic_2027": 30,
            "tcp_2027": 40,
        }
    )

    # Modern transports are independent public underlays. No old base transport
    # is automatically created for a new managed tunnel.
    tunnel_managed._TRANSPORTS = ()
    tunnel_managed._SELECTION_ORDER = MODERN_SELECTION_ORDER
    tunnel_managed._run_relay_job = _skip_pre_overlay_relay
    tunnel_managed._install_tp2027_phase = _install_tp2027_phase_v18
    tunnel_managed.install_tp2027_overlays = install_tp2027_overlays_v18
    tunnel_managed.diagnose_managed_tunnel = diagnose_managed_tunnel_v18

    managed_ops.DIRECT_BASE_ORDER = ()
    managed_ops.EXPECTED_ORDER = MODERN_EXPECTED_ORDER
    managed_ops.install_tp2027_overlays = install_tp2027_overlays_v18
    managed_ops.diagnose_managed_tunnel = diagnose_managed_tunnel_v18
    managed_ops._repair_managed_tunnel_locked = _repair_managed_tunnel_locked_v18

    print(
        "TWINPANEL_MODERN_RUNTIME_V18_ACTIVE "
        "underlay=public-direct multi_exit=1 legacy_autoprovision=0",
        flush=True,
    )
