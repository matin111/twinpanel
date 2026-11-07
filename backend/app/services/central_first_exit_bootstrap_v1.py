"""Central-first bootstrap of a brand-new hidden Exit.

Only initial daemon/listener installation is performed here. No legacy
subscription backfill, account SSH loops, implicit publication, or copying
protocol settings from existing Exits. Final customer access is exclusively
owned by the central stage after full readiness and credential-coverage audit.
"""
from __future__ import annotations

from fastapi import HTTPException

from ..models import Node, NodeStatus, NodeType
from .new_node_quota_bootstrap_v1 import bootstrap_fresh_hidden_exit_quota


async def bootstrap_hidden_central_exit(payload, request, db) -> dict:
    if payload.node_type != NodeType.EXIT or not payload.defer_subscription_sync:
        raise RuntimeError("CENTRAL_BOOTSTRAP_REQUIRES_HIDDEN_EXIT")
    from ..routers import provision as prov

    if (db.query(Node).filter(
            Node.retired_at.is_(None), Node.name == payload.name
            ).first() is not None):
        raise HTTPException(status_code=409,detail="نام سرور قبلاً ثبت شده است")

    conn = await prov.ssh_connect(payload)
    try:
        os_id = await prov.cmd(
            conn, '. /etc/os-release && printf "%s" "$ID"',
        )
        if os_id not in {"ubuntu","debian"}:
            raise HTTPException(
                status_code=400,
                detail="فعلاً Ubuntu/Debian پشتیبانی می‌شود",
            )
        await prov.ensure_base(conn)
        node = Node(
            name=payload.name, node_type=NodeType.EXIT,
            country_code=payload.country_code.upper(), public_ip=payload.host,
            agent_url=f"https://{payload.host}:9443",
            status=NodeStatus.OFFLINE, show_to_users=False,
            capacity_users=payload.capacity_users,
            enable_cisco=False, enable_openvpn=False,
            enable_wireguard=False, enable_l2tp=False, enable_v2ray=False,
        )
        db.add(node)
        db.commit()
        db.refresh(node)

        # The existing low-level installers are reusable. The LEGACY
        # install_node orchestrator, automatic repair loop and all legacy
        # per-subscription provisioning are intentionally not invoked.
        results, failed, _ = await prov.provision_protocols(
            conn, payload, db, node, False,
        )
        agent = await prov._install_or_upgrade_agent(
            conn, node.id, prov.api_base_url(db, request),
        )
        await prov._ensure_node_key_on_remote(
            conn, db, node, payload.port, payload.username,
        )
        fabric = {"ok": False, "service": "not_installed"}
        try:
            fabric = await prov._install_tunnel_fabric_base(conn, node)
        except Exception as exc:
            fabric = {
                "ok": False, "service": "failed",
                "error_type": type(exc).__name__,
            }
        quota = bootstrap_fresh_hidden_exit_quota(db, node.id)
        if not quota.get("ok"):
            failed = list(failed) + ["quota"]

        return {
            "ok": not failed, "node_id": int(node.id),
            "node_name": node.name, "protocols": results,
            "failed_protocols": list(failed),
            "agent": agent, "quota": quota, "fabric": fabric,
            "subscription_sync": {
                "ok": True, "skipped": True,
                "reason": "central_runtime_owns_all_subscriptions",
            },
            "installation_authority": "central_runtime_v1",
        }
    finally:
        conn.close()
        await conn.wait_closed()
