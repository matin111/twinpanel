from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Tunnel, TunnelTransport
from ..smart_transport_auto_v21 import (
    CANDIDATE_STABLE_SECONDS,
    _smart_state,
    auto_block_reason,
)
from ..transport_candidates import (
    SPECS,
    catalog,
    install_transport,
    runtime,
    uninstall_transport,
)

router = APIRouter(
    prefix="/v1/tunnels",
    tags=["tunnel-modern-transports"],
    dependencies=[Depends(require_admin)],
)


_PROFILE = {
    "kernel_gre": {
        "iran_profile": "direct-gre",
        "description": "Kernel GRE full-L3; lowest overhead when protocol 47 is usable.",
    },
    "gost_tun": {
        "iran_profile": "tun-over-wss",
        "description": "Full-L3 GOST TUN over WebSocket transport; web-like TCP carrier for restrictive paths.",
    },
    "amneziawg": {
        "iran_profile": "obfuscated-udp",
        "description": "Obfuscated WireGuard-style L3 path for UDP-capable networks.",
    },
    "netrix": {
        "iran_profile": "licensed-multipath",
        "description": "Licensed TUN/multipath candidate; enabled only when the controller binary is present.",
    },
}


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _candidate_view(
    *,
    name: str,
    row: TunnelTransport | None,
    tunnel_id: int,
) -> dict:
    state = _smart_state(row) if row is not None else {}
    block = auto_block_reason(row) if row is not None else None

    stable_seconds = 0.0
    try:
        stable_seconds = max(
            0.0,
            float(state.get("stable_seconds") or 0.0),
        )
    except (TypeError, ValueError):
        stable_seconds = 0.0

    throughput = state.get("throughput")
    if not isinstance(throughput, dict):
        throughput = None

    benchmark_fresh = False
    benchmark_age = None
    if throughput is not None:
        try:
            measured = float(throughput.get("measured_at_epoch") or 0.0)
            if measured > 0:
                benchmark_age = max(0.0, time.time() - measured)
                benchmark_fresh = benchmark_age <= 1800.0
        except (TypeError, ValueError):
            pass

    online = bool(
        row is not None
        and bool(row.enabled)
        and _status(row.status) == "online"
    )

    qualified = bool(
        online
        and not block
        and stable_seconds >= float(CANDIDATE_STABLE_SECONDS)
    )

    return {
        "runtime": runtime(name, tunnel_id),
        "enabled": bool(row.enabled) if row else False,
        "status": _status(row.status) if row else "not_installed",
        "latency_ms": row.latency_ms if row else None,
        "last_error": row.last_error if row else None,
        "last_healthy_at": (
            row.last_healthy_at.isoformat()
            if row and row.last_healthy_at
            else None
        ),
        "canary": True,
        "auto_managed": True,
        "qualified": qualified,
        "selectable": qualified,
        "stable_seconds": round(stable_seconds, 1),
        "required_stable_seconds": int(CANDIDATE_STABLE_SECONDS),
        "auto_block_reason": block,
        "quarantine_until_epoch": state.get("quarantine_until_epoch"),
        "benchmark": throughput,
        "benchmark_fresh": benchmark_fresh,
        "benchmark_age_seconds": (
            round(benchmark_age, 1)
            if benchmark_age is not None
            else None
        ),
        **_PROFILE.get(name, {}),
    }


@router.get("/transport-catalog")
def transport_catalog():
    return {
        "ok": True,
        "production_default": "smart_auto",
        "promotion_policy": "health_then_speed",
        "download_weight": 0.70,
        "upload_weight": 0.30,
        "transports": [
            {
                **spec,
                **_PROFILE.get(str(spec["transport"]), {}),
                "auto_managed": True,
            }
            for spec in catalog()
        ],
    }


@router.get("/{tunnel_id}/modern-transports")
def list_modern_transports(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    rows = {
        str(row.transport): row
        for row in db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport.in_(tuple(SPECS)),
        )
        .all()
    }

    output = []
    for spec in catalog():
        name = str(spec["transport"])
        row = rows.get(name)
        output.append(
            {
                **spec,
                **_candidate_view(
                    name=name,
                    row=row,
                    tunnel_id=tunnel_id,
                ),
            }
        )

    return {
        "ok": True,
        "tunnel_id": tunnel_id,
        "mode": tunnel.mode,
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "production_default": "smart_auto",
        "promotion_policy": "health_then_speed",
        "transports": output,
    }


@router.post("/{tunnel_id}/modern-transports/{transport}/install")
async def install_modern_transport(
    tunnel_id: int,
    transport: str,
    db: Session = Depends(get_db),
):
    name = str(transport or "").strip().lower()
    if name not in SPECS:
        raise HTTPException(status_code=404, detail="Unknown modern transport")

    try:
        return await install_transport(name, tunnel_id, db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"{SPECS[name]['label']} canary failed",
                "transport": name,
                "error": str(exc)[:7000],
            },
        ) from exc


@router.delete("/{tunnel_id}/modern-transports/{transport}")
async def remove_modern_transport(
    tunnel_id: int,
    transport: str,
    db: Session = Depends(get_db),
):
    name = str(transport or "").strip().lower()
    if name not in SPECS:
        raise HTTPException(status_code=404, detail="Unknown modern transport")

    if str(tunnel_id).strip() == "":
        raise HTTPException(status_code=400, detail="Invalid tunnel id")

    try:
        return await uninstall_transport(name, tunnel_id, db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"{SPECS[name]['label']} removal failed",
                "transport": name,
                "error": str(exc)[:4000],
            },
        ) from exc
