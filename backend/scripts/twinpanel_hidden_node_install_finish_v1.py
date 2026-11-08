#!/usr/bin/env python3
"""Durable, guarded 16-protocol finisher for a PRE-EXISTING hidden Exit.

Called by systemd-run with only node ID + progress job ID, never a password.
No new node is created, no old certificates are deleted, no customer UUIDs are
rotated, no bulk account SSH from this installer. Only after all 16 actual live
listeners are verified may central admission schedule customer staging.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.getLogger("asyncssh").setLevel(logging.WARNING)

from app.database import SessionLocal
from app.models import Node, NodeProtocolConfig, NodeStatus
from app.protocol_account_registry import ALL_PROTOCOL_KEYS, CLASSIC_PROTOCOL_KEYS
from app.routers.classic_protocol_admin_v1 import (
    EnsureClassicProtocolIn, ensure_classic_protocol,
)
from app.services.hidden_node_install_supervisor_v1 import require_hidden_job
from app.services.node_install_progress_v1 import set_install_progress
from app.services.new_node_modern_bootstrap_v1 import bootstrap_new_exit_modern_protocols
from app.services.new_node_readiness_v1 import verify_new_exit_readiness


def _status(job_id: str, stage: str, node_id: int, **kwargs) -> None:
    set_install_progress(job_id, stage, node_id=node_id, **kwargs)


def _count_staged(db: Session, node_id: int) -> int:
    rows = db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.node_id == node_id,
        NodeProtocolConfig.protocol.in_(list(ALL_PROTOCOL_KEYS)),
    ).all()
    return sum(
        str(getattr(row.status, "value", row.status)).lower() == "online"
        for row in rows
    )


async def finish(node_id: int, job_id: str, *, xray_port: int,
                 publish_to_all_users: bool) -> dict:
    db = SessionLocal()
    stage = "installing_xray"
    try:
        node, job = require_hidden_job(db, node_id, job_id)
        if node.show_to_users:
            raise RuntimeError("NODE_FINISH_VISIBLE_NODE_REFUSED")
        xray_row = db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == node_id,
            NodeProtocolConfig.protocol == "v2ray",
        ).first()
        if (
            xray_row is None
            or str(getattr(xray_row.status, "value", xray_row.status)).lower() != "online"
            or not node.enable_v2ray
        ):
            _status(job_id, stage, node_id, installed_protocols=_count_staged(db,node_id))
            try:
                await asyncio.wait_for(
                    ensure_classic_protocol(
                        EnsureClassicProtocolIn(
                            node_id=node_id, protocol="v2ray", port=xray_port,
                        ),
                        db=db,
                    ),
                    timeout=660,
                )
                print("HIDDEN_NODE_XRAY_INSTALLED", {"node_id": node_id}, flush=True)
            except Exception as exc:
                db.rollback()
                print("HIDDEN_NODE_XRAY_INSTALL_DEGRADED", {
                    "node_id": node_id, "error_type": type(exc).__name__,
                    # No private remote error output in a published job.
                }, flush=True)
        db.expire_all()
        node, _ = require_hidden_job(db, node_id, job_id)

        # Classic Xray package/bootstrap alone can leave a single legacy
        # plaintext VLESS inbound. It is NOT enough for customer V2Ray.
        # This is a brand-new HIDDEN Exit with no client memberships: enable
        # and verify the three real XHTTP/Reality/TCP-or-TLS profiles before
        # accepting customer traffic. Existing nodes are never touched here.
        xray_row = db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == node_id,
            NodeProtocolConfig.protocol == "v2ray",
        ).first()
        if (
            xray_row is not None and node.enable_v2ray
            and str(getattr(xray_row.status, "value", xray_row.status)).lower()
            == "online"
        ):
            from app import xray_modern_runtime
            from app.routers import account_delivery as ad
            conn = None
            try:
                conn = await asyncio.wait_for(ad.ssh_connect_saved(node,db),timeout=20)
                base_port = int(xray_row.port or xray_port)
                state = await asyncio.wait_for(
                    xray_modern_runtime._ensure_modern_xray(
                        conn,base_port,node,
                    ),timeout=300,
                )
                profiles = list(state.get("available_profiles") or [])
                if len(set(profiles)) < 3:
                    raise RuntimeError("XRAY_THREE_CUSTOMER_PROFILES_NOT_READY")
                print("HIDDEN_NODE_XRAY_THREE_INBOUNDS_VERIFIED", {
                    "node_id":node_id,"count":len(set(profiles)),
                },flush=True)
            except Exception as exc:
                print("HIDDEN_NODE_XRAY_MODERN_PROFILES_DEGRADED", {
                    "node_id":node_id,"error_type":type(exc).__name__,
                },flush=True)
            finally:
                if conn is not None:
                    conn.close()
                    await conn.wait_closed()
        db.expire_all()
        node, _ = require_hidden_job(db, node_id, job_id)

        stage = "installing_modern"
        _status(job_id, stage, node_id, installed_protocols=_count_staged(db,node_id))

        def checkpoint(installed: list[str], failed: list[str],
                       already: list[str]) -> None:
            _status(
                job_id, "installing_modern", node_id,
                installed_protocols=_count_staged(db,node_id),
            )

        modern = await bootstrap_new_exit_modern_protocols(
            db, node_id, on_progress=checkpoint,
        )
        print("HIDDEN_NODE_MODERN_GROUPS_COMPLETE", {
            "node_id": node_id,
            "attempted": modern.get("attempted",0),
            "failed": modern.get("failed",[]),
            "missing_templates": len(modern.get("skipped_no_template",[])),
            "port_conflicts": len(modern.get("skipped_port_conflict",[])),
        }, flush=True)
        db.expire_all()
        node, _ = require_hidden_job(db, node_id, job_id)

        # The final gate is based on 16 actual listener health probes,
        # never DB online flags or a fabricated 100% progress bar.
        readiness = await verify_new_exit_readiness(db, node_id)
        ready_count = int(readiness.get("ready_count") or 0)
        if not readiness.get("ok"):
            _status(job_id, "failed", node_id,
                    installed_protocols=ready_count,
                    error_code="PROTOCOL_SETUP_INCOMPLETE")
            print("HIDDEN_NODE_READINESS_NOT_VERIFIED", {
                "node_id": node_id,
                "missing": readiness.get("missing",[]),
                "reason": readiness.get("reason"),
                "visible": False,
            }, flush=True)
            return {"ok": False, "node_id": node_id,
                    "missing": readiness.get("missing",[]),
                    "reason": readiness.get("reason")}

        from app.services.new_node_quota_bootstrap_v1 import (
            bootstrap_fresh_hidden_exit_quota,
        )
        quota = bootstrap_fresh_hidden_exit_quota(db, node_id)
        if not quota.get("ok"):
            _status(job_id, "failed", node_id, installed_protocols=ready_count,
                    error_code="NODE_QUOTA_SETUP_FAILED")
            return {"ok": False, "reason": "NODE_QUOTA_SETUP_FAILED"}

        stage = "verified_ready"
        _status(job_id,stage,node_id,installed_protocols=ready_count)
        if publish_to_all_users:
            from app.services.central_progressive_exit_admission_v1 import (
                admit_verified_exit, hide_after_dispatch_failure,
            )
            from app.services.central_node_stage_launcher_v1 import launch
            node = db.get(Node, node_id)
            if node.status != NodeStatus.MAINTENANCE:
                node.status = NodeStatus.ONLINE
            db.commit()
            stage = "enrolling_users"
            _status(job_id,stage,node_id,installed_protocols=ready_count)
            try:
                admission=admit_verified_exit(db,node_id)
                scheduled=launch(db,node_id,initial_full=True)
            except Exception:
                db.rollback()
                hide_after_dispatch_failure(db,node_id)
                _status(job_id,"failed",node_id,
                        installed_protocols=ready_count,
                        error_code="CENTRAL_BACKGROUND_DISPATCH_FAILED")
                print("HIDDEN_NODE_CENTRAL_DISPATCH_SAFE_STOP",
                      {"node_id":node_id},flush=True)
                return {"ok":False,"reason":"CENTRAL_BACKGROUND_DISPATCH_FAILED"}
            _status(job_id,"completed",node_id,
                    installed_protocols=ready_count,
                    users_assigned=int(admission["eligible_users"]))
            print("HIDDEN_NODE_CENTRAL_PUBLISH_SUCCESS",{
                "node_id":node_id,
                "users_assigned":int(admission["eligible_users"]),
                "daemon_unit":scheduled["unit"],
                "customer_credential_coverage_verified":False,
            },flush=True)
        else:
            _status(job_id,"completed",node_id,
                    installed_protocols=ready_count)
            print("HIDDEN_NODE_VERIFIED_UNPUBLISHED",{
                "node_id":node_id, "published":False,
            },flush=True)
        return {"ok":True,"node_id":node_id,"listeners_ready":ready_count}
    except Exception as exc:
        db.rollback()
        from app.services.node_os_preflight_v1 import safe_node_install_error_code
        code=safe_node_install_error_code(exc)
        _status(job_id,"failed",node_id,error_code=code)
        print("HIDDEN_NODE_FINISH_FAILED", {
            "node_id":node_id,"stage":stage,
            "error_code":code,"error_type":type(exc).__name__,
        },flush=True)
        return {"ok":False,"node_id":node_id,"error_code":code}
    finally:
        db.close()


def parse(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--node-id",required=True,type=int)
    ap.add_argument("--job-id",required=True)
    ap.add_argument("--xray-port",type=int,default=8443)
    ap.add_argument("--publish-to-all-users",action="store_true")
    ap.add_argument("--apply",action="store_true")
    ap.add_argument("--confirm-node-id",type=int)
    args=ap.parse_args(argv)
    if (args.node_id<=0 or not args.apply
            or args.node_id!=args.confirm_node_id
            or not 1<=args.xray_port<=65535):
        ap.error("explicit --apply and exact --confirm-node-id required")
    return args


def main(argv=None):
    args=parse(argv)
    result=asyncio.run(finish(
        args.node_id,args.job_id,xray_port=args.xray_port,
        publish_to_all_users=args.publish_to_all_users,
    ))
    return 0 if result.get("ok") else 2


if __name__=="__main__":
    raise SystemExit(main())
