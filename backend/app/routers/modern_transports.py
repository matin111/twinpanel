from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..managed_deep_diagnostics_v32 import deep_diagnose_managed_tunnel
from ..managed_ops import repair_managed_tunnel
from ..models import Tunnel, TunnelTransport
from ..transport_candidates import SPECS, catalog, install_transport, runtime, uninstall_transport

router = APIRouter(
    prefix="/v1/tunnels",
    tags=["tunnel-modern-transports"],
    dependencies=[Depends(require_admin)],
)


@router.get("/transport-catalog")
def transport_catalog():
    return {
        "ok": True,
        "production_default": "backhaul",
        "promotion_policy": "canary-first",
        "transports": catalog(),
    }


@router.get("/{tunnel_id}/modern-transports")
def list_modern_transports(tunnel_id: int, db: Session = Depends(get_db)):
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
                "runtime": runtime(name, tunnel_id),
                "enabled": bool(row.enabled) if row else False,
                "status": str(row.status) if row else "not_installed",
                "latency_ms": row.latency_ms if row else None,
                "last_error": row.last_error if row else None,
                "last_healthy_at": row.last_healthy_at.isoformat() if row and row.last_healthy_at else None,
                "canary": True,
                "selectable": False,
            }
        )

    return {
        "ok": True,
        "tunnel_id": tunnel_id,
        "active_transport": tunnel.active_transport,
        "production_default": "backhaul",
        "transports": output,
    }


@router.get("/{tunnel_id}/managed-deep-diagnose")
async def managed_deep_diagnose(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """Read-only, panel-driven data-plane diagnosis on both tunnel nodes."""
    try:
        return await deep_diagnose_managed_tunnel(tunnel_id, db)
    except RuntimeError as exc:
        if str(exc) == "tunnel_not_found":
            raise HTTPException(status_code=404, detail="Tunnel not found") from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/{tunnel_id}/managed-deep-repair")
async def managed_deep_repair(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """Run managed repair, include missed modern paths, then deep-diagnose.

    V32 deliberately does not rotate ports, keys, MTUs, Auto weights or policy
    thresholds. It reuses each transport's canonical installer only when that
    transport is already enabled but unhealthy, and returns the read-only
    post-repair data-plane diagnosis to the panel.
    """
    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    managed_result = None
    managed_error = None
    try:
        managed_result = await repair_managed_tunnel(tunnel_id, db)
    except Exception as exc:
        db.rollback()
        managed_error = f"{type(exc).__name__}: {str(exc)[:1800]}"

    db.expire_all()
    modern_results: dict[str, object] = {}
    modern_errors: dict[str, str] = {}

    for name in ("kernel_gre", "gost_tun"):
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == tunnel_id,
                TunnelTransport.transport == name,
            )
            .first()
        )
        if row is None or not bool(row.enabled):
            continue
        if str(row.status or "").strip().lower() == "online":
            modern_results[name] = {"skipped": True, "reason": "already_online"}
            continue

        try:
            modern_results[name] = await install_transport(name, tunnel_id, db)
        except Exception as exc:
            db.rollback()
            modern_errors[name] = f"{type(exc).__name__}: {str(exc)[:1800]}"

    db.expire_all()
    diagnosis = await deep_diagnose_managed_tunnel(tunnel_id, db)

    return {
        "ok": not bool(managed_error) and not bool(modern_errors),
        "tunnel_id": tunnel_id,
        "managed_repair": managed_result,
        "managed_error": managed_error,
        "modern_repair": modern_results,
        "modern_errors": modern_errors,
        "deep_diagnosis": diagnosis,
        "marker": "TWINPANEL_MANAGED_DEEP_REPAIR_V32_ACTIVE",
        "safety": {
            "ports_rotated": False,
            "keys_rotated": False,
            "mtu_changed": False,
            "auto_weights_changed": False,
            "hysteresis_changed": False,
        },
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
