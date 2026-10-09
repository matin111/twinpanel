from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
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
