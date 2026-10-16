from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..agent_diagnostics_v33 import desired_targets_for_node, save_agent_report
from ..config import settings
from ..database import get_db
from ..models import Node, Tunnel


router = APIRouter(
    prefix="/v1/tunnel-diagnostics",
    tags=["tunnel-diagnostics-agent-v33"],
)


class DiagnosticsReportIn(BaseModel):
    agent_version: str = Field(default="unknown", max_length=64)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


def _require_node_secret(value: str | None) -> None:
    if value != settings.node_agent_shared_secret:
        raise HTTPException(status_code=401, detail="Invalid node secret")


@router.get("/node/{node_id}/desired")
def diagnostics_desired(
    node_id: int,
    x_node_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_node_secret(x_node_secret)

    node = db.get(Node, int(node_id))
    if node is None or getattr(node, "retired_at", None) is not None:
        raise HTTPException(status_code=404, detail="Node not found")

    return desired_targets_for_node(int(node_id), db)


@router.post("/tunnel/{tunnel_id}/node/{node_id}/report")
def diagnostics_report(
    tunnel_id: int,
    node_id: int,
    payload: DiagnosticsReportIn,
    x_node_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_node_secret(x_node_secret)

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    if int(node_id) not in {
        int(tunnel.iran_node_id),
        int(tunnel.exit_node_id),
    }:
        raise HTTPException(status_code=403, detail="Node does not belong to tunnel")

    allowed = {"kcp_2027", "mtunnel", "kernel_gre", "gost_tun"}
    diagnostics = {
        str(name): value
        for name, value in payload.diagnostics.items()
        if str(name) in allowed and isinstance(value, dict)
    }

    try:
        save_agent_report(
            int(tunnel_id),
            int(node_id),
            agent_version=payload.agent_version,
            diagnostics=diagnostics,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Diagnostics cache unavailable: {type(exc).__name__}: {str(exc)[:300]}",
        ) from exc

    return {
        "ok": True,
        "tunnel_id": int(tunnel_id),
        "node_id": int(node_id),
        "accepted": sorted(diagnostics),
        "marker": "TWINPANEL_AGENT_DIAGNOSTICS_REPORT_V33_ACTIVE",
    }
