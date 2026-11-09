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
    # This was only a duplicate-name SELECT on a brand-new, private
    # background SessionLocal with no staged writes. Release its read
    # transaction BEFORE SSH, apt and remote protocol installation; otherwise
    # PostgreSQL holds an idle-in-transaction connection for minutes.
    db.rollback()

    conn = await prov.ssh_connect(payload)
    try:
        # Previous Exit installs sourced /etc/os-release and aborted in
        # ~2 seconds on an otherwise reachable Finnish node. Use the same
        # read-only /etc -> /usr/lib -> lsb_release fallback as SSH Test.
        # No remote mutation and no DB node creation before this succeeds.
        await prov.remote_supported_os_id(conn)
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
        # Persist the dedicated hostname *before* the detached Xray installer
        # reads this newly created Exit. Never confuse the shared Iran/public
        # tunnel hostname with a verified node-owned TLS identity.
        domain = str(getattr(payload, "xray_domain", None) or "").strip().lower()
        if domain:
            if "xray_domain" not in Node.__table__.c:
                raise RuntimeError("XRAY_NEW_EXIT_DOMAIN_SCHEMA_NOT_READY")
            node.xray_domain = domain
        db.add(node)
        # Flush allocates Node.id while the first write transaction is open.
        # SessionLocal uses expire_on_commit=False, so refresh() would only
        # start an unnecessary SELECT transaction before slow SSH installs.
        db.flush()
        db.commit()

        # The existing low-level installers are reusable. The LEGACY
        # install_node orchestrator, automatic repair loop and all legacy
        # per-subscription provisioning are intentionally not invoked.
        results, failed, _ = await prov.provision_protocols(
            conn, payload, db, node, False,
        )
        wireguard_pool = {"ok": True, "skipped": True}
        if payload.install_wireguard and "wireguard" not in failed:
            from .central_new_exit_wireguard_pool_v1 import (
                prepare_hidden_exit_wireguard_pool,
            )
            try:
                wireguard_pool = await prepare_hidden_exit_wireguard_pool(conn)
            except Exception as exc:
                wireguard_pool = {
                    "ok": False,
                    "reason": "central_pool_preparation_failed",
                    "error_type": type(exc).__name__,
                }
                failed = list(failed) + ["wireguard_pool"]

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
            "wireguard_pool": wireguard_pool,
            "subscription_sync": {
                "ok": True, "skipped": True,
                "reason": "central_runtime_owns_all_subscriptions",
            },
            "installation_authority": "central_runtime_v1",
        }
    finally:
        conn.close()
        await conn.wait_closed()
