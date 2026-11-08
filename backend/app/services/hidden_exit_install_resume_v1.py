"""Resume a hidden, interrupted Exit's POST-base install with saved node SSH.

No base reinstall, no imported-user conversion, no rebuilding healthy
credentials and no automatic exposure. Each incomplete protocol is handled
by the existing idempotent managed installer and verified against LIVE listeners
before optional central admission. Designed for the detached worker only.
"""
from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Node, NodeType, NodeProtocolConfig
from .node_install_progress_v1 import set_install_progress


def _progress(job_id: str, stage: str, **extra: Any) -> None:
    try:
        set_install_progress(job_id,stage,**extra)
    except Exception as exc:
        print("NODE_RESUME_PROGRESS_WRITE_FAILED",{
            "error_type":type(exc).__name__,"stage":stage,
        },flush=True)


def _ready_count(db: Session, node_id: int) -> int:
    from ..protocol_account_registry import ALL_PROTOCOL_KEYS
    rows=db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.node_id==int(node_id),
        NodeProtocolConfig.protocol.in_(list(ALL_PROTOCOL_KEYS)),
    ).all()
    return sum(
        str(getattr(r.status,"value",r.status) or "").lower()=="online"
        for r in rows
    )


async def resume_hidden_exit(
    *,node_id:int,job_id:str,publish_to_all_users:bool=False,
) -> None:
    db=SessionLocal()
    try:
        node=db.get(Node,int(node_id))
        if (node is None or node.retired_at is not None
                or node.node_type!=NodeType.EXIT or node.show_to_users):
            raise RuntimeError("NODE_RESUME_REQUIRES_HIDDEN_EXIT")

        # No server-wide install or global Xray restart.
        _progress(job_id,"installing_xray",node_id=node_id,
                  installed_protocols=_ready_count(db,node_id))
        row=(db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id==node_id,
            NodeProtocolConfig.protocol=="v2ray",
        ).first())
        if (row is None or
                str(getattr(row.status,"value",row.status) or "").lower()!="online"):
            from ..routers.classic_protocol_admin_v1 import (
                EnsureClassicProtocolIn,ensure_classic_protocol,
            )
            try:
                await asyncio.wait_for(
                    ensure_classic_protocol(
                        EnsureClassicProtocolIn(
                            node_id=node_id,protocol="v2ray",
                            port=int(row.port) if row and row.port else 8443,
                        ),db=db,
                    ),timeout=240,
                )
            except Exception as exc:
                db.rollback()
                print("NODE_RESUME_XRAY_UNAVAILABLE",{
                    "node_id":node_id,"error_type":type(exc).__name__,
                },flush=True)

        _progress(job_id,"installing_modern",node_id=node_id,
                  installed_protocols=_ready_count(db,node_id))
        from .new_node_modern_bootstrap_v1 import bootstrap_new_exit_modern_protocols
        try:
            modern=await asyncio.wait_for(
                bootstrap_new_exit_modern_protocols(
                    db=db,node_id=node_id,
                    on_group_complete=lambda _: _progress(
                        job_id,"installing_modern",node_id=node_id,
                        installed_protocols=_ready_count(db,node_id),
                    ),
                ),
                timeout=1800,
            )
            print("NODE_RESUME_MODERN_GROUPS",{
                "node_id":node_id,
                "attempted":modern.get("attempted"),
                "installed":modern.get("installed"),
                "failed":modern.get("failed"),
            },flush=True)
        except Exception as exc:
            db.rollback()
            print("NODE_RESUME_MODERN_FAILED",{
                "node_id":node_id,"error_type":type(exc).__name__,
            },flush=True)

        # This is the only authority for readiness: DB online flags alone
        # cannot certify that all 16 listeners are accepting connections.
        from .new_node_readiness_v1 import verify_new_exit_readiness
        live=await verify_new_exit_readiness(db,node_id)
        count=int(live.get("ready_count") or 0)
        if not live.get("ok"):
            _progress(job_id,"failed",node_id=node_id,
                      installed_protocols=count,
                      error_code="PROTOCOL_SETUP_INCOMPLETE")
            print("NODE_RESUME_HIDDEN_NOT_READY",{
                "node_id":node_id,"missing":live.get("missing") or [],
                "reason":live.get("reason"),
            },flush=True)
            return

        _progress(job_id,"verified_ready",node_id=node_id,
                  installed_protocols=count)
        if not publish_to_all_users:
            _progress(job_id,"completed",node_id=node_id,
                      installed_protocols=count)
            print("NODE_RESUME_VERIFIED_HIDDEN",{
                "node_id":node_id,"ready":count,
                "node_visible":False,
            },flush=True)
            return

        from .central_progressive_exit_admission_v1 import (
            admit_verified_exit,hide_after_dispatch_failure,
        )
        from .central_node_stage_launcher_v1 import launch as launch_central_stage
        from ..models import NodeStatus
        _progress(job_id,"enrolling_users",node_id=node_id,
                  installed_protocols=count)
        node=db.get(Node,node_id)
        if node and node.status!=NodeStatus.MAINTENANCE:
            node.status=NodeStatus.ONLINE
        db.commit()
        try:
            admitted=admit_verified_exit(db,node_id)
            dispatched=launch_central_stage(db,node_id,initial_full=True)
        except Exception:
            db.rollback()
            hide_after_dispatch_failure(db,node_id)
            _progress(job_id,"failed",node_id=node_id,
                      installed_protocols=count,
                      error_code="CENTRAL_BACKGROUND_DISPATCH_FAILED")
            return
        _progress(job_id,"completed",node_id=node_id,
                  installed_protocols=count,
                  users_assigned=int(admitted["eligible_users"]))
        print("NODE_RESUME_CENTRAL_ADMISSION_COMPLETE",{
            "node_id":node_id,"users":admitted["eligible_users"],
            "unit":dispatched.get("unit"),
        },flush=True)
    except Exception as exc:
        db.rollback()
        from .node_os_preflight_v1 import safe_node_install_error_code
        code=safe_node_install_error_code(exc)
        _progress(job_id,"failed",node_id=node_id,
                  error_code=code)
        print("NODE_RESUME_WORKER_FAILED",{
            "node_id":node_id,"error_type":type(exc).__name__,
            "error_code":code,
        },flush=True)
    finally:
        db.close()
