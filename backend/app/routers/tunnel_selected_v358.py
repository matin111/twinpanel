from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import (
    Node,
    NodeStatus,
    NodeType,
    Tunnel,
    TunnelPeerState,
    TunnelStatus,
)
from ..transport_candidates import uninstall_transport
from . import tunnels as core
from .modern_transports import (
    SpoofWGConfiguration,
    configure_spoof_wg,
    install_modern_transport,
    select_modern_transport_manual,
)
from .tunnel_managed import _iran_provision_lock, _remove_failed_new_tunnel


# TWINPANEL_SELECTED_INITIAL_TRANSPORT_V358
router = APIRouter(
    prefix="/v1/tunnels",
    tags=["tunnel-selected-create-v358"],
    dependencies=[Depends(require_admin)],
)


class SelectedTunnelCreateV358(BaseModel):
    iran_node_id: int
    exit_node_id: int
    priority: int = 100
    initial_transport: Literal["tp27_fast", "spoof_wg"] = "tp27_fast"
    iran_spoof_ip: str | None = None
    exit_spoof_ip: str | None = None


def _node_status(node: Node) -> str:
    return str(getattr(node.status, "value", node.status) or "").strip().lower()


def _resolve_ready_pair(
    db: Session,
    payload: SelectedTunnelCreateV358,
) -> tuple[Node, Node]:
    iran = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == int(payload.iran_node_id),
        )
        .first()
    )
    exit_node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == int(payload.exit_node_id),
        )
        .first()
    )

    if (
        iran is None
        or iran.node_type != NodeType.IRAN
        or getattr(iran, "is_mother", False)
        or getattr(iran, "agent_url", None) == "local://core"
        or str(iran.public_ip or "").strip() in {"127.0.0.1", "localhost"}
    ):
        raise HTTPException(status_code=400, detail="سرور ایران معتبر نیست")

    if exit_node is None or exit_node.node_type != NodeType.EXIT:
        raise HTTPException(status_code=400, detail="سرور خروجی معتبر نیست")

    if _node_status(iran) != NodeStatus.ONLINE.value:
        raise HTTPException(
            status_code=409,
            detail="سرور ایران باید قبل از ساخت Tunnel آنلاین باشد",
        )

    if _node_status(exit_node) != NodeStatus.ONLINE.value:
        raise HTTPException(
            status_code=409,
            detail="سرور خروجی باید قبل از ساخت Tunnel آنلاین باشد",
        )

    existing = (
        db.query(Tunnel)
        .filter(
            Tunnel.iran_node_id == int(iran.id),
            Tunnel.exit_node_id == int(exit_node.id),
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "برای این Iran/Exit از قبل Tunnel وجود دارد",
                "tunnel_id": int(existing.id),
            },
        )

    return iran, exit_node


def _create_clean_pair(
    db: Session,
    *,
    iran: Node,
    exit_node: Node,
    payload: SelectedTunnelCreateV358,
) -> Tunnel:
    selected = str(payload.initial_transport)
    tunnel = Tunnel(
        iran_node_id=int(iran.id),
        exit_node_id=int(exit_node.id),
        # Compatibility only. Physical authority remains active_transport.
        transport=selected,
        priority=int(payload.priority),
        is_active=False,
        status=TunnelStatus.OFFLINE,
        latency_ms=None,
        wireguard_port=None,
        mode="manual",
        preferred_transport=None,
        active_transport=None,
    )
    db.add(tunnel)
    db.flush()

    db.add_all(
        [
            TunnelPeerState(
                tunnel_id=int(tunnel.id),
                node_id=int(iran.id),
                selected_transport=selected,
                endpoint_reachable=False,
                tunnel_reachable=False,
                last_error="not_installed",
            ),
            TunnelPeerState(
                tunnel_id=int(tunnel.id),
                node_id=int(exit_node.id),
                selected_transport=selected,
                endpoint_reachable=False,
                tunnel_reachable=False,
                last_error="not_installed",
            ),
        ]
    )
    db.commit()
    db.refresh(tunnel)
    return tunnel


async def _rollback_new_selected_tunnel(
    db: Session,
    *,
    tunnel_id: int,
    transport: str,
) -> None:
    try:
        await uninstall_transport(transport, int(tunnel_id), db)
    except BaseException:
        db.rollback()

    try:
        await _remove_failed_new_tunnel(db, int(tunnel_id))
    except BaseException:
        db.rollback()
        # Last-resort DB cleanup is deliberately limited to this brand-new pair.
        db.query(TunnelPeerState).filter(
            TunnelPeerState.tunnel_id == int(tunnel_id)
        ).delete(synchronize_session=False)
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is not None:
            db.delete(tunnel)
        db.commit()


@router.post(
    "/create-selected",
    dependencies=[Depends(require_admin)],
)
async def create_selected_tunnel_v358(
    payload: SelectedTunnelCreateV358,
    db: Session = Depends(get_db),
):
    """Create one logical pair and provision exactly one selected modern path.

    Other Smart Transport candidates are intentionally left uninstalled and may
    be added later from /admin/tunnel-transports. The legacy /create-managed
    multi-transport behavior remains unchanged for compatibility.
    """

    selected = str(payload.initial_transport).strip().lower()

    if selected == "spoof_wg":
        if not str(payload.iran_spoof_ip or "").strip() or not str(
            payload.exit_spoof_ip or ""
        ).strip():
            raise HTTPException(
                status_code=422,
                detail="برای Spoof Tunnel هر دو IP Spoof ایران و خارج الزامی است",
            )

    async with _iran_provision_lock(int(payload.iran_node_id)):
        iran, exit_node = _resolve_ready_pair(db, payload)
        tunnel = _create_clean_pair(
            db,
            iran=iran,
            exit_node=exit_node,
            payload=payload,
        )
        tunnel_id = int(tunnel.id)

        try:
            # Reuse the authoritative controller-driven Agent + Tunnel Fabric
            # bootstrap already used by existing tunnel installers.
            iran_bootstrap = await core._ensure_fabric_for_tunnel_node(iran, db)
            exit_bootstrap = await core._ensure_fabric_for_tunnel_node(exit_node, db)

            if not iran_bootstrap.get("ok") or not exit_bootstrap.get("ok"):
                raise RuntimeError("node_bootstrap_not_ready")

            await core._tp_managed_preflight_pair(iran, exit_node, db)

            spoof_configuration = None
            if selected == "spoof_wg":
                spoof_configuration = configure_spoof_wg(
                    tunnel_id,
                    SpoofWGConfiguration(
                        iran_spoof_ip=str(payload.iran_spoof_ip).strip(),
                        exit_spoof_ip=str(payload.exit_spoof_ip).strip(),
                    ),
                    db,
                )

            install_result = await install_modern_transport(
                tunnel_id,
                selected,
                db,
            )

            # TWINPANEL_SELECTED_AGENT_VISIBILITY_V359
            # /node/{node_id}/desired intentionally publishes only is_active
            # tunnels. A brand-new selected pair starts inactive/offline so it
            # stays outside production route election during bootstrap/install.
            # Once the selected transport has installed successfully, publish
            # the pair to both Agents before V257 waits for their fresh reports.
            # Keep status OFFLINE and active_transport unset here: service-route
            # election requires ONLINE, so this visibility step cannot promote
            # user traffic before the existing manual cutover safety gate.
            db.expire_all()
            pending = db.get(Tunnel, tunnel_id)
            if pending is None:
                raise RuntimeError("created_tunnel_missing_before_agent_visibility")
            pending.is_active = True
            db.commit()
            db.refresh(pending)

            # Reuse V257/V289 fresh full-L3 probe + post-switch Agent
            # acceptance + rollback authority. No custom cutover is invented.
            selection_result = await select_modern_transport_manual(
                tunnel_id,
                selected,
                db,
            )

            db.expire_all()
            live = db.get(Tunnel, tunnel_id)
            if live is None:
                raise RuntimeError("created_tunnel_missing_after_selection")

            return {
                "ok": True,
                "operational": True,
                "tunnel": {
                    "id": int(live.id),
                    "iran_node_id": int(live.iran_node_id),
                    "exit_node_id": int(live.exit_node_id),
                    "priority": int(live.priority),
                    "mode": live.mode,
                    "status": getattr(live.status, "value", live.status),
                    "active_transport": live.active_transport,
                    "preferred_transport": live.preferred_transport,
                },
                "initial_transport": selected,
                "installed": [selected],
                "other_transports": "not_installed",
                "spoof_configuration": spoof_configuration,
                "bootstrap": {
                    "iran": iran_bootstrap,
                    "exit": exit_bootstrap,
                },
                "install": install_result,
                "selection": selection_result,
            }

        except HTTPException:
            await _rollback_new_selected_tunnel(
                db,
                tunnel_id=tunnel_id,
                transport=selected,
            )
            raise
        except Exception as exc:
            await _rollback_new_selected_tunnel(
                db,
                tunnel_id=tunnel_id,
                transport=selected,
            )
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "ساخت Tunnel با مسیر انتخابی کامل نشد و Pair جدید rollback شد",
                    "transport": selected,
                    "error": str(exc)[:1800],
                    "rolled_back": True,
                },
            ) from exc
