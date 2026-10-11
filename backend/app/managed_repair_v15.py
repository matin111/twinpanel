from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from .managed_ops import (
    DIRECT_BASE_ORDER,
    _merge_unresolved_errors,
    _repair_base_job,
    _repair_relay_job,
    _row_online,
    _rows,
    diagnose_managed_tunnel,
)
from .models import Tunnel
from .tp2027_provision import TP2027_PRIORITY, install_tp2027_overlays


async def repair_managed_tunnel(tunnel_id: int, db: Session) -> dict:
    """Panel-owned managed repair with deterministic installer ordering.

    Existing installers remain the single source of truth for node setup.
    This orchestration deliberately runs remote-mutating base installers one
    at a time so repair cannot race systemd/interface/firewall changes.
    """

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    tunnel.mode = "auto"
    tunnel.is_active = True
    db.commit()

    before = diagnose_managed_tunnel(int(tunnel_id), db)
    need = set(before["repair_needed"])

    base_targets = [
        name for name in DIRECT_BASE_ORDER if name in need
    ]
    base_results: dict[str, object] = {}
    errors: dict[str, str] = {}

    for name in base_targets:
        item_name, online, error, result = await _repair_base_job(
            name,
            int(tunnel_id),
        )
        if result is not None:
            base_results[item_name] = result
        if not online and error:
            errors[item_name] = error

    db.expire_all()
    rows = _rows(db, tunnel_id)
    direct_online = any(
        _row_online(rows.get(name))
        for name in DIRECT_BASE_ORDER
    )

    relay_result = None
    if not direct_online:
        name, relay_ok, relay_error, relay_result = await _repair_relay_job(
            int(tunnel_id)
        )
        if relay_result is not None:
            base_results[name] = relay_result
        if not relay_ok and relay_error:
            errors[name] = relay_error

    db.expire_all()
    rows = _rows(db, tunnel_id)
    backhaul_online = _row_online(rows.get("backhaul"))

    overlay_result = None
    overlay_needed = any(name in need for name in TP2027_PRIORITY)

    if overlay_needed and backhaul_online:
        try:
            overlay_result = await asyncio.wait_for(
                install_tp2027_overlays(int(tunnel_id), db),
                timeout=240,
            )
        except Exception as exc:
            db.rollback()
            message = str(exc)[:1800]
            for name in TP2027_PRIORITY:
                errors[name] = message

    elif overlay_needed and not backhaul_online:
        for name in TP2027_PRIORITY:
            errors[name] = "carrier_down: backhaul is not online"

    await asyncio.sleep(12)
    db.expire_all()
    after = diagnose_managed_tunnel(int(tunnel_id), db)
    errors = _merge_unresolved_errors(after, errors)

    operational = bool(after.get("operational"))
    attempted = bool(base_targets or overlay_needed or not direct_online)
    partial = bool(operational and after.get("repair_needed"))

    return {
        "ok": operational,
        "healthy": operational,
        "operational": operational,
        "complete": bool(after.get("complete")),
        "partial": partial,
        "tunnel_id": int(tunnel_id),
        "mode": "auto",
        "provisioning_mode": "panel_serial_v15",
        "before": before,
        "after": after,
        "base_results": base_results,
        "ssh_relay_result": relay_result,
        "tp2027_result": overlay_result,
        "errors": errors,
        "remaining": list(after.get("repair_needed") or []),
        "attempted": attempted,
        "repaired_at": datetime.utcnow().isoformat() + "Z",
    }
