from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_admin
from .routers.modern_transports import router
from .tp27_self_repair_v265 import diagnose_tp27, repair_tp27


MARKER = "TWINPANEL_TP27_REPAIR_API_V265"
_applied = False


def _http_error(exc: Exception) -> HTTPException:
    value = str(exc or "")
    if value == "tunnel_not_found":
        return HTTPException(status_code=404, detail="Tunnel not found")
    if value == "tp27_not_installed":
        return HTTPException(status_code=404, detail="TP27 Fast is not installed")
    if value == "tp27_disabled":
        return HTTPException(status_code=409, detail="TP27 Fast is disabled")
    return HTTPException(status_code=502, detail=value[:1800] or type(exc).__name__)


def apply_tp27_repair_api_v265() -> None:
    """Attach TP27 carrier tools to the already-registered modern router.

    main.py imports modern_transports before apply_self_hosted_runtime() is
    called, so adding these routes here keeps the public router composition
    additive and avoids a second competing /v1/tunnels router owner.
    """

    global _applied
    if _applied:
        return

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
        f"{MARKER}_ACTIVE endpoints=diagnose,repair,rebuild",
        flush=True,
    )
