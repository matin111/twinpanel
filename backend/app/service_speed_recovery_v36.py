from __future__ import annotations

import json
import math
import time
from typing import Any

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .auto_eligibility_v24 import auto_eligible
from .database import get_db
from .deps import require_admin
from .models import Tunnel, TunnelStatus, TunnelTransport
from .routers import tunnels
from .xray_profile_reconcile_v36 import (
    get_xray_reconcile_job,
    start_xray_reconcile_job,
)


# TWINPANEL_SERVICE_SPEED_RECOVERY_V36
#
# Service forwarding stays on the existing kernel iptables DNAT/SNAT path.
# This runtime does NOT add a userspace proxy and does not alter MTU/keys/ports.
# It only gives the panel a safe way to return a logical tunnel to AUTO and,
# when fresh manager telemetry already has usable members, immediately seeds the
# aggregate tunnel with the best-known member while the normal manager remains
# authoritative on subsequent cycles.

_runtime_applied = False
_THROUGHPUT_TTL_SECONDS = 1800.0


def _status(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _config(row: TunnelTransport) -> dict[str, Any]:
    raw = getattr(row, "config_text", None)
    if not raw:
        return {}

    try:
        value = json.loads(str(raw))
    except Exception:
        return {}

    return value if isinstance(value, dict) else {}


def _fresh_throughput(row: TunnelTransport) -> float | None:
    data = _config(row).get("auto_throughput")
    if not isinstance(data, dict):
        return None

    try:
        measured = float(data.get("measured_at_epoch"))
        effective = float(data.get("effective_mbps"))
    except (TypeError, ValueError):
        return None

    if not math.isfinite(measured) or not math.isfinite(effective):
        return None
    if measured <= 0 or effective <= 0:
        return None
    if max(0.0, time.time() - measured) > _THROUGHPUT_TTL_SECONDS:
        return None

    return effective


def _candidate_payload(row: TunnelTransport) -> dict[str, Any]:
    throughput = _fresh_throughput(row)
    return {
        "transport": str(row.transport or "").strip().lower(),
        "priority": int(row.priority or 9999),
        "latency_ms": row.latency_ms,
        "effective_mbps": round(throughput, 3) if throughput is not None else None,
    }


def _rank_candidates(rows: list[TunnelTransport]) -> list[TunnelTransport]:
    usable = [
        row
        for row in rows
        if bool(row.enabled)
        and _status(row.status) == "online"
    ]

    auto_rows = [row for row in usable if auto_eligible(row)]
    if auto_rows:
        usable = auto_rows

    fresh_count = sum(1 for row in usable if _fresh_throughput(row) is not None)

    def key(row: TunnelTransport):
        throughput = _fresh_throughput(row)
        latency = (
            int(row.latency_ms)
            if row.latency_ms is not None
            else 10**9
        )
        priority = int(row.priority or 9999)
        row_id = int(row.id or 0)

        if fresh_count >= 2:
            return (
                0 if throughput is not None else 1,
                -(throughput or 0.0),
                latency,
                priority,
                row_id,
            )

        return (
            0,
            0.0,
            latency,
            priority,
            row_id,
        )

    return sorted(usable, key=key)


async def high_speed_auto_route(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")

    if not bool(tunnel.is_active):
        tunnel.is_active = True

    rows = (
        db.query(TunnelTransport)
        .filter(TunnelTransport.tunnel_id == int(tunnel_id))
        .order_by(TunnelTransport.priority.asc(), TunnelTransport.id.asc())
        .all()
    )

    ranked = _rank_candidates(rows)

    # AUTO is the key change: a failed manually pinned MTunnel must not keep the
    # entire USA service path down when another healthy transport is available.
    tunnel.mode = "auto"

    selected = ranked[0] if ranked else None
    if selected is not None:
        name = str(selected.transport or "").strip().lower()
        tunnel.active_transport = name
        tunnel.preferred_transport = name
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = selected.latency_ms
        tunnel.last_switch_at = __import__("datetime").datetime.utcnow()
    else:
        tunnel.status = TunnelStatus.OFFLINE
        tunnel.latency_ms = None

    db.commit()
    db.refresh(tunnel)

    return {
        "ok": True,
        "tunnel_id": int(tunnel.id),
        "mode": "auto",
        "route_ready": selected is not None,
        "active_transport": str(tunnel.active_transport or ""),
        "status": _status(tunnel.status),
        "latency_ms": tunnel.latency_ms,
        "selection_basis": (
            "fresh_throughput"
            if sum(1 for row in ranked if _fresh_throughput(row) is not None) >= 2
            else "healthy_latency"
        ),
        "candidates": [_candidate_payload(row) for row in ranked],
        "message": (
            "مسیر AUTO با سریع‌ترین عضو سالم فعال شد؛ Agent قوانین سرویس را در چرخه بعدی اعمال می‌کند"
            if selected is not None
            else "حالت AUTO فعال شد اما هنوز Transport سالمی برای عبور سرویس وجود ندارد"
        ),
    }


async def start_tunnel_xray_reconcile(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")

    return await start_xray_reconcile_job(int(tunnel.exit_node_id))


def tunnel_xray_reconcile_status(
    tunnel_id: int,
    job_id: str,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")

    return get_xray_reconcile_job(str(job_id), int(tunnel.exit_node_id))


def apply_service_speed_recovery_v36() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    routes = {
        (getattr(route, "path", ""), tuple(sorted(getattr(route, "methods", None) or ())))
        for route in tunnels.router.routes
    }

    definitions = [
        (
            "/{tunnel_id}/service-connections/high-speed-auto",
            high_speed_auto_route,
            ["POST"],
            "High-speed automatic service route",
        ),
        (
            "/{tunnel_id}/service-connections/xray-reconcile-job",
            start_tunnel_xray_reconcile,
            ["POST"],
            "Reconcile Xray profiles for tunnel Exit",
        ),
        (
            "/{tunnel_id}/service-connections/xray-reconcile-job/{job_id}",
            tunnel_xray_reconcile_status,
            ["GET"],
            "Xray profile reconciliation job status",
        ),
    ]

    for path, endpoint, methods, summary in definitions:
        key = (path, tuple(sorted(methods)))
        if key in routes:
            raise RuntimeError(f"V36 route already registered: {path}")

        tunnels.router.add_api_route(
            path,
            endpoint,
            methods=methods,
            dependencies=[Depends(require_admin)],
            summary=summary,
        )

    _runtime_applied = True

    print(
        "TWINPANEL_SERVICE_SPEED_RECOVERY_V36_ACTIVE "
        "kernel_forwarding=1 userspace_proxy=0 xray_job=1",
        flush=True,
    )
