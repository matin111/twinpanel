from __future__ import annotations

import asyncio
import time
from typing import Any

from . import xray_modern_runtime, xray_profile_reconcile_v36
from .database import SessionLocal
from .models import Node, NodeProtocolConfig, NodeType
from .routers import account_delivery, provision
from .xray_tcp_tls_v39 import _tcp_tls_target_port


# TWINPANEL_XRAY_RECONCILE_INFRA_V41
#
# V39 made TCP TLS part of profile completeness. Existing credentials can
# therefore already contain the tcp_tls profile while the Exit listener is
# still absent (for example after a deployment that added the profile metadata
# before the remote Xray runtime was rebuilt). V36 reconciliation then sees the
# credentials as complete and skips every subscription, so _ensure_modern_xray
# is never called and the listener remains missing forever.
#
# V41 fixes the layer ordering: before a background profile reconcile scans
# subscriptions, it verifies the Exit TCP TLS listener. If missing, it invokes
# the final production _ensure_modern_xray binding once. At runtime this is the
# V39 wrapper, so the existing Xray config is validated, clients/UUIDs are
# preserved, TCP TLS is installed, and the listener is verified before normal
# subscription reconciliation continues.

_runtime_applied = False
_original_run_reconcile_job = None


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


async def _prepare_exit_tcp_tls_runtime(
    job_id: str,
    exit_node_id: int,
) -> None:
    db = SessionLocal()

    try:
        job = xray_profile_reconcile_v36._jobs.get(str(job_id))
        if job is not None:
            job["status"] = "running"
            job["infrastructure"] = {
                "status": "checking",
                "profile": "tcp_tls",
            }

        node = db.get(Node, int(exit_node_id))
        if node is None or node.node_type != NodeType.EXIT:
            raise RuntimeError("exit_node_not_found")

        cfg = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id == int(exit_node_id),
                NodeProtocolConfig.protocol == "v2ray",
            )
            .first()
        )

        if (
            not bool(getattr(node, "enable_v2ray", False))
            or cfg is None
            or _enum_value(cfg.status) != "online"
        ):
            raise RuntimeError("exit_xray_not_online")

        base_port = int(
            cfg.port
            or account_delivery.DEFAULT_PORTS["v2ray"]
        )
        target_port = _tcp_tls_target_port(base_port)

        conn = await account_delivery.ssh_connect_saved(node, db)

        try:
            if await provision.listener(conn, target_port, "tcp"):
                result = {
                    "status": "already_ready",
                    "profile": "tcp_tls",
                    "target_port": target_port,
                    "changed": False,
                }
            else:
                state = await xray_modern_runtime._ensure_modern_xray(
                    conn,
                    base_port,
                    node,
                )

                listener_ok = bool(
                    await provision.listener(
                        conn,
                        target_port,
                        "tcp",
                    )
                )

                if not listener_ok:
                    raise RuntimeError(
                        f"tcp_tls_listener_missing_after_repair:{target_port}"
                    )

                result = {
                    "status": "repaired",
                    "profile": "tcp_tls",
                    "target_port": target_port,
                    "changed": True,
                    "available_profiles": list(
                        state.get("available_profiles") or []
                    ),
                }

        finally:
            conn.close()
            await conn.wait_closed()

        if job is not None:
            job["infrastructure"] = result

    finally:
        db.close()


async def _run_reconcile_job_v41(
    job_id: str,
    exit_node_id: int,
) -> None:
    assert _original_run_reconcile_job is not None

    try:
        await _prepare_exit_tcp_tls_runtime(
            str(job_id),
            int(exit_node_id),
        )

    except asyncio.CancelledError:
        raise

    except Exception as exc:
        job = xray_profile_reconcile_v36._jobs.get(str(job_id))

        if job is not None:
            job["status"] = "failed"
            job["finished_at_epoch"] = time.time()
            job["error"] = (
                "xray_infrastructure_repair_failed: "
                + str(exc)[:1400]
            )
            job["infrastructure"] = {
                "status": "failed",
                "profile": "tcp_tls",
                "error": str(exc)[:1200],
            }

        async with xray_profile_reconcile_v36._job_lock:
            if (
                xray_profile_reconcile_v36._running_by_exit.get(
                    int(exit_node_id)
                )
                == str(job_id)
            ):
                xray_profile_reconcile_v36._running_by_exit.pop(
                    int(exit_node_id),
                    None,
                )

        return

    await _original_run_reconcile_job(
        str(job_id),
        int(exit_node_id),
    )


def apply_xray_reconcile_infra_v41() -> None:
    global _runtime_applied
    global _original_run_reconcile_job

    if _runtime_applied:
        return

    _original_run_reconcile_job = (
        xray_profile_reconcile_v36._run_reconcile_job
    )
    xray_profile_reconcile_v36._run_reconcile_job = (
        _run_reconcile_job_v41
    )

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_RECONCILE_INFRA_V41_ACTIVE "
        "tcp_tls_listener_preflight=1 background=1 uuid_preserved=1",
        flush=True,
    )
