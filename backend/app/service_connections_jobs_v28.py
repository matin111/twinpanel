from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_admin
from .models import Tunnel
from .routers import tunnels
from .xray_customer_xhttp_v46 import apply_xray_customer_xhttp_v46
from .xray_profile_reconcile_v36 import (
    get_xray_reconcile_job,
    start_xray_reconcile_job,
)


_runtime_applied = False


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


def apply_service_connections_jobs_v28() -> None:
    global _runtime_applied
    if _runtime_applied:
        return

    # self_hosted_runtime invokes this after the final V30 customer profile
    # policy and after the V41 infrastructure wrapper are installed. Activate
    # V46 here so the Xray reconcile endpoints capture the final customer
    # contract: WebSocket TLS -> XHTTP Reality -> TCP TLS. V46 extends the
    # existing V41/V36 reconcile chain; it does not replace it.
    apply_xray_customer_xhttp_v46()

    definitions = [
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

    existing = {
        (
            str(getattr(route, "path", "") or ""),
            tuple(sorted(getattr(route, "methods", None) or ())),
        )
        for route in tunnels.router.routes
    }

    for path, endpoint, methods, summary in definitions:
        key = (path, tuple(sorted(methods)))
        if key in existing:
            raise RuntimeError(f"Service-connections job route already registered: {path}")
        tunnels.router.add_api_route(
            path,
            endpoint,
            methods=methods,
            dependencies=[Depends(require_admin)],
            summary=summary,
        )

    _runtime_applied = True
    print(
        "TWINPANEL_SERVICE_CONNECTIONS_JOBS_V28_ACTIVE "
        "xray_job=1 xhttp_customer_policy_v46=1",
        flush=True,
    )
