from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agent_diagnostics_v33 import (
    build_agent_diagnosis,
    install_agent_on_connection,
)
from ..database import get_db
from ..deps import require_admin
from ..managed_ops import repair_managed_tunnel
from ..models import Node, Tunnel, TunnelTransport
from ..services.public_urls import api_base_url
from ..transport_candidates import SPECS, catalog, install_transport, runtime, uninstall_transport
from .provision import ssh_connect_saved

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
def managed_deep_diagnose(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """Read-only V33 diagnosis assembled from node-local diagnostics agents.

    No SSH connection is opened by this endpoint. Missing/stale agent data is
    returned as an agent_unavailable result with HTTP 200 so one bad node never
    takes down the whole diagnostics page.
    """
    try:
        return build_agent_diagnosis(tunnel_id, db)
    except RuntimeError as exc:
        if str(exc) == "tunnel_not_found":
            raise HTTPException(status_code=404, detail="Tunnel not found") from exc
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Agent diagnostics unavailable: {type(exc).__name__}: {str(exc)[:500]}",
        ) from exc


@router.post("/{tunnel_id}/managed-deep-agent-install")
async def managed_deep_agent_install(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """One-click install/upgrade of the dedicated diagnostics agent.

    Saved SSH credentials are used only for this installation/recovery step.
    Normal diagnostics then run locally on each node and push reports back to
    TwinPanel without inbound agent ports or routine SSH.
    """
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    iran = db.get(Node, int(tunnel.iran_node_id))
    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if iran is None or exit_node is None:
        raise HTTPException(status_code=409, detail="Tunnel nodes are missing")

    api_base = api_base_url(db, None)
    ci = ce = None
    results: dict[str, object] = {}

    try:
        connected = await asyncio.gather(
            ssh_connect_saved(iran, db),
            ssh_connect_saved(exit_node, db),
            return_exceptions=True,
        )

        ci = connected[0] if not isinstance(connected[0], Exception) else None
        ce = connected[1] if not isinstance(connected[1], Exception) else None

        if ci is None:
            results["iran"] = {
                "ok": False,
                "node_id": int(iran.id),
                "error": f"SSH connect failed: {connected[0]}",
            }
        if ce is None:
            results["exit"] = {
                "ok": False,
                "node_id": int(exit_node.id),
                "error": f"SSH connect failed: {connected[1]}",
            }

        jobs = []
        labels = []
        if ci is not None:
            jobs.append(install_agent_on_connection(ci, int(iran.id), api_base))
            labels.append("iran")
        if ce is not None:
            jobs.append(install_agent_on_connection(ce, int(exit_node.id), api_base))
            labels.append("exit")

        if jobs:
            installed = await asyncio.gather(*jobs, return_exceptions=True)
            for label, value in zip(labels, installed):
                if isinstance(value, Exception):
                    results[label] = {
                        "ok": False,
                        "error": f"{type(value).__name__}: {str(value)[:1200]}",
                    }
                else:
                    results[label] = value

    finally:
        for conn in (ci, ce):
            if conn is not None:
                conn.close()
                await conn.wait_closed()

    ok = bool(
        isinstance(results.get("iran"), dict)
        and results["iran"].get("ok") is True
        and isinstance(results.get("exit"), dict)
        and results["exit"].get("ok") is True
    )

    return {
        "ok": ok,
        "tunnel_id": int(tunnel_id),
        "results": results,
        "routine_ssh_required": False,
        "inbound_agent_port_required": False,
        "marker": "TWINPANEL_AGENT_DIAGNOSTICS_INSTALL_V33_ACTIVE",
    }


@router.post("/{tunnel_id}/managed-deep-repair")
async def managed_deep_repair(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """Run existing managed repair, then read node-agent diagnosis.

    V33 keeps the existing repair implementation for compatibility but removes
    controller-side SSH from the post-repair diagnostic. Ports, keys, MTUs,
    Auto weights and hysteresis are not rotated by this wrapper.
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
    diagnosis = build_agent_diagnosis(tunnel_id, db)

    return {
        "ok": not bool(managed_error) and not bool(modern_errors),
        "tunnel_id": tunnel_id,
        "managed_repair": managed_result,
        "managed_error": managed_error,
        "modern_repair": modern_results,
        "modern_errors": modern_errors,
        "deep_diagnosis": diagnosis,
        "marker": "TWINPANEL_MANAGED_DEEP_REPAIR_V33_ACTIVE",
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


# Register the node-authenticated V33 agent routes on the same exported router
# without inheriting the admin dependency attached to routes created above.
# APIRoute objects below were built by an independent router and are appended
# directly so their X-Node-Secret authentication remains authoritative.
from .tunnel_diagnostics_agent_v33 import router as _diagnostics_agent_router

router.routes.extend(_diagnostics_agent_router.routes)
