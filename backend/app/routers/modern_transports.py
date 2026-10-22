from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Tunnel, TunnelStatus, TunnelTransport
from ..smart_transport_auto_v21 import (
    CANDIDATE_STABLE_SECONDS,
    _smart_state,
    auto_block_reason,
)
from ..transport_candidates import (
    ACTIVE_SPECS,
    SPECS,
    catalog,
    install_transport,
    runtime,
    uninstall_transport,
)
from ..transport_candidates import spoof_wg

router = APIRouter(
    prefix="/v1/tunnels",
    tags=["tunnel-modern-transports"],
    dependencies=[Depends(require_admin)],
)


_PROFILE = {
    "tp27_fast": {
        "iran_profile": "tp27-auto-gre",
        "description": (
            "TP27 Fast full-L3: keyed native GRE first, then GRE/UDP FoU "
            "fallback with fail-closed health and throughput qualification."
        ),
    },
    "spoof_wg": {
        "iran_profile": "mutual-ip-spoof + wireguard-l3",
        "description": (
            "Spoof Tunnel v3.1 core carries a private WireGuard /30. "
            "Mutual spoof source addresses must be configured explicitly and "
            "the path is accepted only after TwinPanel full-L3 qualification."
        ),
    },
    # Legacy migration-only descriptions remain available for cleanup paths.
    "kernel_gre": {
        "iran_profile": "direct-gre-retired",
        "description": "Retired migration fallback; removed after TP27 Fast promotion.",
    },
}


class SpoofWGConfiguration(BaseModel):
    iran_spoof_ip: str
    exit_spoof_ip: str


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

    extra: dict = {}
    if name == "spoof_wg":
        configuration = spoof_wg.configuration_for_view(
            row.config_text if row is not None else None
        )
        extra = {
            "configuration": configuration,
            "configured": bool(configuration.get("configured")),
            "configuration_required": not bool(configuration.get("configured")),
            "auto_install": False,
            "xdp": False,
            "upstream_version": spoof_wg.UPSTREAM_VERSION,
        }

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
        **extra,
        **_PROFILE.get(name, {}),
    }


@router.get("/transport-catalog")
def transport_catalog():
    return {
        "ok": True,
        "production_default": "manual",
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
            TunnelTransport.transport.in_(tuple(ACTIVE_SPECS)),
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
        "production_default": "manual",
        "promotion_policy": "health_then_speed",
        "transports": output,
    }


@router.put("/{tunnel_id}/modern-transports/spoof_wg/config")
def configure_spoof_wg(
    tunnel_id: int,
    payload: SpoofWGConfiguration,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    try:
        configuration = spoof_wg.validate_configuration(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport == "spoof_wg",
        )
        .first()
    )

    if row is not None and _status(row.status) == "installing":
        raise HTTPException(
            status_code=409,
            detail="Spoof Tunnel installation is currently running",
        )
    if row is not None and bool(row.enabled) and _status(row.status) == "online":
        raise HTTPException(
            status_code=409,
            detail="Remove the online Spoof Tunnel before changing its spoof addresses",
        )

    if row is None:
        row = TunnelTransport(
            tunnel_id=tunnel_id,
            transport="spoof_wg",
            priority=int(ACTIVE_SPECS["spoof_wg"]["priority"]),
            enabled=False,
            status="not_installed",
        )
        db.add(row)
        db.flush()

    row.priority = int(ACTIVE_SPECS["spoof_wg"]["priority"])
    row.enabled = False
    row.status = "not_installed"
    row.latency_ms = None
    row.last_error = None
    row.config_text = spoof_wg.merge_configuration(
        row.config_text,
        configuration,
    )
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "tunnel_id": tunnel_id,
        "transport": "spoof_wg",
        "configuration": spoof_wg.configuration_for_view(row.config_text),
        "next": "install",
    }


# TWINPANEL_MANUAL_MODERN_TRANSPORT_V192
@router.post("/{tunnel_id}/modern-transports/{transport}/select-manual")
def select_modern_transport_manual(
    tunnel_id: int,
    transport: str,
    db: Session = Depends(get_db),
):
    name = str(transport or "").strip().lower()
    if name not in ACTIVE_SPECS:
        raise HTTPException(
            status_code=404,
            detail="Unknown or retired modern transport",
        )

    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport == name,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Transport not installed")

    if not bool(row.enabled):
        raise HTTPException(status_code=400, detail="Transport disabled")

    view = _candidate_view(
        name=name,
        row=row,
        tunnel_id=tunnel_id,
    )
    if not bool(view.get("selectable")):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Transport is not qualified for manual production selection",
                "transport": name,
                "status": view.get("status"),
                "stable_seconds": view.get("stable_seconds"),
                "required_stable_seconds": view.get("required_stable_seconds"),
                "auto_block_reason": view.get("auto_block_reason"),
            },
        )

    tunnel.mode = "manual"
    tunnel.active_transport = name
    tunnel.preferred_transport = name
    tunnel.status = TunnelStatus.ONLINE
    tunnel.latency_ms = row.latency_ms

    db.commit()
    db.refresh(tunnel)

    return {
        "ok": True,
        "tunnel_id": int(tunnel.id),
        "mode": tunnel.mode,
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "status": _status(tunnel.status),
        "latency_ms": tunnel.latency_ms,
        "transport": name,
    }


@router.post("/{tunnel_id}/modern-transports/{transport}/install")
async def install_modern_transport(
    tunnel_id: int,
    transport: str,
    db: Session = Depends(get_db),
):
    name = str(transport or "").strip().lower()
    if name not in ACTIVE_SPECS:
        raise HTTPException(status_code=404, detail="Unknown or retired modern transport")

    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    if name == "spoof_wg":
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == tunnel_id,
                TunnelTransport.transport == name,
            )
            .first()
        )
        if row is None or spoof_wg.configuration_from_text(row.config_text) is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Spoof Tunnel requires Iran and Exit spoof IPv4 addresses before install",
                    "transport": name,
                    "configuration_required": True,
                },
            )

    try:
        return await install_transport(name, tunnel_id, db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"{ACTIVE_SPECS[name]['label']} canary failed",
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
    if name not in SPECS and name not in {"gost_tun", "amneziawg", "netrix"}:
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
                "message": f"{name} removal failed",
                "transport": name,
                "error": str(exc)[:4000],
            },
        ) from exc
