from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from . import smart_transport_auto_v21 as smart
from .database import get_db
from .deps import require_admin
from .models import Tunnel, TunnelTransport
from .routers.modern_transports import router
from .tp27_self_repair_v265 import diagnose_tp27, repair_tp27
from .transport_candidates import ACTIVE_SPECS


MARKER = "TWINPANEL_TP27_REPAIR_API_V265"
_applied = False


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _http_error(exc: Exception) -> HTTPException:
    value = str(exc or "")
    if value == "tunnel_not_found":
        return HTTPException(status_code=404, detail="Tunnel not found")
    if value == "tp27_not_installed":
        return HTTPException(status_code=404, detail="TP27 Fast is not installed")
    if value == "tp27_disabled":
        return HTTPException(status_code=409, detail="TP27 Fast is disabled")
    return HTTPException(status_code=502, detail=value[:1800] or type(exc).__name__)


async def _fresh_transport_probe(
    tunnel_id: int,
    transport: str,
    db: Session,
) -> dict:
    name = str(transport or "").strip().lower()
    if name not in ACTIVE_SPECS:
        raise HTTPException(
            status_code=404,
            detail="Unknown or retired modern transport",
        )

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == name,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Transport not installed")
    if not bool(row.enabled):
        raise HTTPException(status_code=409, detail="Transport is disabled")

    key = (int(tunnel_id), name)
    smart._candidate_health_cache.pop(key, None)

    try:
        probed_name, health = await smart.candidate_health_remote_v21(
            int(tunnel_id),
            name,
            {},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Fresh transport health probe failed",
                "transport": name,
                "error": str(exc)[:2500],
                "production_path_unchanged": True,
            },
        ) from exc

    if str(probed_name or "").strip().lower() != name:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Health probe returned a different transport",
                "transport": name,
                "probed_transport": str(probed_name),
                "production_path_unchanged": True,
            },
        )

    db.expire_all()
    tunnel = db.get(Tunnel, int(tunnel_id))
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == name,
        )
        .first()
    )

    if tunnel is None or row is None:
        raise HTTPException(
            status_code=409,
            detail="Tunnel or transport changed during health probe",
        )

    return {
        "ok": bool((health or {}).get("ok")),
        "marker": "TWINPANEL_TRANSPORT_CARD_PROBE_V266",
        "tunnel_id": int(tunnel.id),
        "transport": name,
        "mode": tunnel.mode,
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "production_path_unchanged": True,
        "status": _status(row.status),
        "latency_ms": row.latency_ms,
        "last_error": row.last_error,
        "last_healthy_at": (
            row.last_healthy_at.isoformat()
            if row.last_healthy_at
            else None
        ),
        "health": dict(health or {}),
    }


def apply_tp27_repair_api_v265() -> None:
    """Attach per-transport health tools and TP27 carrier repair controls.

    main.py imports modern_transports before apply_self_hosted_runtime() is
    called, so adding these routes here keeps the public router composition
    additive and avoids a second competing /v1/tunnels router owner.
    """

    global _applied
    if _applied:
        return

    @router.post(
        "/{tunnel_id}/modern-transports/{transport}/probe",
        dependencies=[Depends(require_admin)],
    )
    async def transport_probe(
        tunnel_id: int,
        transport: str,
        db: Session = Depends(get_db),
    ):
        return await _fresh_transport_probe(
            int(tunnel_id),
            transport,
            db,
        )

    @router.get(
        "/{tunnel_id}/tp27/diagnose",
        dependencies=[Depends(require_admin)],
    )
    async def tp27_diagnose(
        tunnel_id: int,
        db: Session = Depends(get_db),
    ):
        try:
            return await diagnose_tp27(int(tunnel_id), db)
        except RuntimeError as exc:
            raise _http_error(exc) from exc

    @router.post(
        "/{tunnel_id}/tp27/repair",
        dependencies=[Depends(require_admin)],
    )
    async def tp27_repair(
        tunnel_id: int,
        db: Session = Depends(get_db),
    ):
        try:
            return await repair_tp27(
                int(tunnel_id),
                db,
                force_rebuild=False,
                source="panel-repair",
            )
        except RuntimeError as exc:
            raise _http_error(exc) from exc

    @router.post(
        "/{tunnel_id}/tp27/rebuild",
        dependencies=[Depends(require_admin)],
    )
    async def tp27_rebuild(
        tunnel_id: int,
        db: Session = Depends(get_db),
    ):
        try:
            return await repair_tp27(
                int(tunnel_id),
                db,
                force_rebuild=True,
                source="panel-rebuild",
            )
        except RuntimeError as exc:
            raise _http_error(exc) from exc

    _applied = True
    print(
        f"{MARKER}_ACTIVE endpoints=transport-probe,tp27-diagnose,tp27-repair,tp27-rebuild",
        flush=True,
    )
