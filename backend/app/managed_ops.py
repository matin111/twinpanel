from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Tunnel, TunnelTransport
from .tp2027_provision import TP2027_PRIORITY, install_tp2027_overlays


EXPECTED_ORDER = (
    "quic_2027",
    "arq_2027",
    "kcp_2027",
    "tcp_2027",
    "mtunnel",
    "backhaul",
    "ssh_tun",
)

BASE_ORDER = (
    "mtunnel",
    "backhaul",
    "ssh_tun",
)

BASE_TIMEOUTS = {
    "mtunnel": 170,
    "backhaul": 90,
    "ssh_tun": 180,
}


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _rows(db: Session, tunnel_id: int) -> dict[str, TunnelTransport]:
    return {
        str(row.transport).strip().lower(): row
        for row in (
            db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == int(tunnel_id))
            .all()
        )
    }


def diagnose_managed_tunnel(tunnel_id: int, db: Session) -> dict:
    """Dependency-aware diagnosis for all managed transports.

    This routine is intentionally read-only. It never changes the selected
    transport, peer health, or runtime state. Transport Manager V7 remains the
    sole runtime health/failover authority.
    """

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    rows = _rows(db, tunnel_id)
    backhaul = rows.get("backhaul")
    backhaul_online = bool(
        backhaul
        and bool(backhaul.enabled)
        and _status(backhaul.status) == "online"
    )

    repair_needed: list[str] = []
    transports: list[dict] = []

    for name in EXPECTED_ORDER:
        row = rows.get(name)
        enabled = bool(row.enabled) if row else False
        status = _status(row.status) if row else "missing"
        issue_code: str | None = None

        if name in TP2027_PRIORITY and not backhaul_online:
            issue_code = "carrier_down"
        elif row is None:
            issue_code = "not_installed"
        elif not enabled:
            issue_code = "disabled"
        elif status != "online":
            issue_code = "unhealthy"

        if issue_code:
            repair_needed.append(name)

        transports.append(
            {
                "transport": name,
                "priority": getattr(row, "priority", None),
                "enabled": enabled,
                "status": status,
                "latency_ms": getattr(row, "latency_ms", None),
                "last_error": getattr(row, "last_error", None),
                "issue_code": issue_code,
                "dependency": "backhaul" if name in TP2027_PRIORITY else None,
            }
        )

    return {
        "ok": True,
        "tunnel_id": int(tunnel.id),
        "mode": str(getattr(tunnel, "mode", "auto") or "auto"),
        "status": _status(getattr(tunnel, "status", "offline")),
        "active_transport": getattr(tunnel, "active_transport", None),
        "preferred_transport": getattr(tunnel, "preferred_transport", None),
        "backhaul_online": backhaul_online,
        "repair_needed": repair_needed,
        "healthy": not repair_needed,
        "transports": transports,
    }


async def install_ssh_transport_managed(tunnel_id: int, db: Session):
    """Official SSH installer used by managed create/repair.

    It deliberately delegates to the existing production installer. Automatic
    repair retries the installer when health is bad; no ad-hoc server mutation
    or manual DB status override is performed here.
    """

    from .routers import tunnels as core

    last_error: Exception | None = None

    for attempt in (1, 2):
        try:
            return await core.install_ssh_transport(int(tunnel_id), db)
        except Exception as exc:
            db.rollback()
            last_error = exc
            if attempt == 1:
                await asyncio.sleep(2)

    assert last_error is not None
    raise last_error


async def _repair_base_job(
    name: str,
    tunnel_id: int,
) -> tuple[str, bool, str | None, object | None]:
    from .routers import tunnels as core

    installers = {
        "mtunnel": core.install_mtunnel_transport,
        "backhaul": core.install_backhaul_transport,
        "ssh_tun": install_ssh_transport_managed,
    }

    db = SessionLocal()
    try:
        try:
            result = await asyncio.wait_for(
                installers[name](int(tunnel_id), db),
                timeout=int(BASE_TIMEOUTS[name]),
            )

            db.expire_all()
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == name,
                )
                .first()
            )
            online = bool(
                row
                and bool(row.enabled)
                and _status(row.status) == "online"
            )

            return (
                name,
                online,
                None if online else "installer_finished_but_transport_not_online",
                result,
            )

        except Exception as exc:
            db.rollback()
            return name, False, str(exc)[:1800], None
    finally:
        db.close()


async def repair_managed_tunnel(tunnel_id: int, db: Session) -> dict:
    """Diagnose and repair missing/unhealthy managed runtime automatically.

    Only installers are invoked. Peer reachability, online/offline state and
    active transport selection are not fabricated here; V7 remains authoritative.
    """

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    # Managed repair returns control to AUTO, but does not select a route.
    tunnel.mode = "auto"
    tunnel.is_active = True
    db.commit()

    before = diagnose_managed_tunnel(int(tunnel_id), db)
    need = set(before["repair_needed"])

    base_targets = [name for name in BASE_ORDER if name in need]
    base_results: dict[str, object] = {}
    errors: dict[str, str] = {}

    if base_targets:
        settled = await asyncio.gather(
            *(
                _repair_base_job(name, int(tunnel_id))
                for name in base_targets
            )
        )

        for name, online, error, result in settled:
            if result is not None:
                base_results[name] = result
            if not online and error:
                errors[name] = error

    db.expire_all()
    rows = _rows(db, tunnel_id)
    backhaul = rows.get("backhaul")
    backhaul_online = bool(
        backhaul
        and bool(backhaul.enabled)
        and _status(backhaul.status) == "online"
    )

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

    # V7 consumes the repaired runtime asynchronously. We only provide a fresh
    # diagnosis snapshot; no active transport/peer health is forced here.
    await asyncio.sleep(3)
    db.expire_all()
    after = diagnose_managed_tunnel(int(tunnel_id), db)

    return {
        "ok": True,
        "tunnel_id": int(tunnel_id),
        "mode": "auto",
        "before": before,
        "after": after,
        "base_results": base_results,
        "tp2027_result": overlay_result,
        "errors": errors,
        "repaired_at": datetime.utcnow().isoformat() + "Z",
    }
