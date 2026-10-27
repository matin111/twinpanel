from __future__ import annotations

import asyncio
import base64
import shlex
from textwrap import dedent

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

# Import V70 first so Exit bootstrap/control-plane behavior remains the base
# authority. This module only refines Iran-node provisioning and Agent install.
from . import node_bootstrap_control_v66 as _bootstrap_v70  # noqa: F401
from .database import SessionLocal, get_db
from .models import Node, NodeAccess, NodeStatus, NodeType
from .routers import provision


MARKER = "TWINPANEL_IRAN_PROVISION_RESILIENCE_V278"
_RUNTIME_APPLIED = False
_BASE_INSTALL_NODE = provision.install_node
_BASE_AGENT_INSTALL = provision._install_or_upgrade_agent


def _active_node_by_name(db: Session, name: str) -> Node | None:
    return (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.name == str(name or "").strip(),
        )
        .first()
    )


def _active_node_by_ip(db: Session, public_ip: str) -> Node | None:
    return (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.public_ip == str(public_ip or "").strip(),
        )
        .first()
    )


def _saved_access(db: Session, node_id: int) -> NodeAccess | None:
    return (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(node_id))
        .first()
    )


async def _ensure_agent_python_v278(conn) -> tuple[str, str]:
    """Return (python_path, dependency_source) without needless PyPI access.

    Existing healthy Agent venvs are reused exactly as-is. For a fresh/broken
    venv, prefer distro-provided python3-httpx/python3-psutil through a
    --system-site-packages venv. PyPI is a bounded last resort and never upgrades
    pip. This keeps transient files.pythonhosted.org DNS failures from breaking
    otherwise healthy Node upgrades.
    """

    await provision.cmd(
        conn,
        "mkdir -p /opt/twinpanel-agent /var/lib/twinpanel-agent",
    )

    existing = await provision.cmd(
        conn,
        "if [ -x /opt/twinpanel-agent/venv/bin/python ] && "
        "/opt/twinpanel-agent/venv/bin/python -c 'import httpx,psutil' "
        ">/dev/null 2>&1; then echo existing_venv; else echo missing; fi",
        check=False,
    )
    if existing.strip() == "existing_venv":
        return "/opt/twinpanel-agent/venv/bin/python", "existing_venv"

    system_ready = await provision.cmd(
        conn,
        "if python3 -c 'import httpx,psutil' >/dev/null 2>&1; "
        "then echo yes; else echo no; fi",
        check=False,
    )

    if system_ready.strip() != "yes":
        # ensure_base() has already proved apt connectivity for first install.
        # On retries this remains bounded and is skipped entirely when imports
        # are already available.
        await provision.cmd(
            conn,
            "export DEBIAN_FRONTEND=noninteractive; "
            "for TRY in 1 2 3; do "
            "apt-get -o DPkg::Lock::Timeout=120 install -y "
            "python3-httpx python3-psutil >/dev/null 2>&1 && exit 0; "
            "sleep 2; done; exit 1",
            timeout=240,
            check=False,
        )
        system_ready = await provision.cmd(
            conn,
            "if python3 -c 'import httpx,psutil' >/dev/null 2>&1; "
            "then echo yes; else echo no; fi",
            check=False,
        )

    if system_ready.strip() == "yes":
        await provision.cmd(
            conn,
            "rm -rf /opt/twinpanel-agent/venv.new; "
            "python3 -m venv --system-site-packages "
            "/opt/twinpanel-agent/venv.new && "
            "/opt/twinpanel-agent/venv.new/bin/python -c "
            "'import httpx,psutil' && "
            "if [ -d /opt/twinpanel-agent/venv ]; then "
            "rm -rf /opt/twinpanel-agent/venv.previous-v278; "
            "mv /opt/twinpanel-agent/venv "
            "/opt/twinpanel-agent/venv.previous-v278; fi && "
            "mv /opt/twinpanel-agent/venv.new /opt/twinpanel-agent/venv",
            timeout=180,
        )
        return "/opt/twinpanel-agent/venv/bin/python", "system_packages"

    # Last resort for minimal distributions: bounded PyPI install, without
    # `pip install --upgrade pip`, which was the observed production failure.
    await provision.cmd(
        conn,
        "rm -rf /opt/twinpanel-agent/venv.new; "
        "python3 -m venv /opt/twinpanel-agent/venv.new && "
        "/opt/twinpanel-agent/venv.new/bin/pip "
        "--disable-pip-version-check install --retries 2 --timeout 15 "
        "'httpx>=0.27,<1' 'psutil>=5.9,<8' >/dev/null && "
        "/opt/twinpanel-agent/venv.new/bin/python -c 'import httpx,psutil' && "
        "if [ -d /opt/twinpanel-agent/venv ]; then "
        "rm -rf /opt/twinpanel-agent/venv.previous-v278; "
        "mv /opt/twinpanel-agent/venv "
        "/opt/twinpanel-agent/venv.previous-v278; fi && "
        "mv /opt/twinpanel-agent/venv.new /opt/twinpanel-agent/venv",
        timeout=180,
    )
    return "/opt/twinpanel-agent/venv/bin/python", "pypi_fallback"


async def _install_iran_agent_v278(
    conn,
    node_id: int,
    api_base: str,
) -> dict:
    python_path, dependency_source = await _ensure_agent_python_v278(conn)

    agent = provision.make_agent(node_id, api_base).encode()
    agent_b64 = base64.b64encode(agent).decode()

    await provision.cmd(
        conn,
        f"printf '%s' {shlex.quote(agent_b64)} | base64 -d "
        "> /opt/twinpanel-agent/agent.py.new",
    )
    await provision.cmd(
        conn,
        f"{shlex.quote(python_path)} -m py_compile "
        "/opt/twinpanel-agent/agent.py.new",
    )
    await provision.cmd(
        conn,
        "if [ -f /opt/twinpanel-agent/agent.py ]; then "
        "cp -f /opt/twinpanel-agent/agent.py "
        "/opt/twinpanel-agent/agent.py.bak; fi && "
        "mv -f /opt/twinpanel-agent/agent.py.new "
        "/opt/twinpanel-agent/agent.py && "
        "chmod 600 /opt/twinpanel-agent/agent.py",
    )

    service = dedent(
        """
        [Unit]
        Description=TwinPanel VPN Node Agent
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=simple
        User=root
        WorkingDirectory=/opt/twinpanel-agent
        ExecStart=/opt/twinpanel-agent/venv/bin/python /opt/twinpanel-agent/agent.py
        Restart=always
        RestartSec=5

        [Install]
        WantedBy=multi-user.target
        """
    ).strip().encode()
    service_b64 = base64.b64encode(service).decode()

    await provision.cmd(
        conn,
        f"printf '%s' {shlex.quote(service_b64)} | base64 -d "
        "> /etc/systemd/system/twinpanel-agent.service.new && "
        "mv -f /etc/systemd/system/twinpanel-agent.service.new "
        "/etc/systemd/system/twinpanel-agent.service && "
        "systemctl daemon-reload && "
        "systemctl enable twinpanel-agent.service >/dev/null && "
        "systemctl restart twinpanel-agent.service",
    )

    await asyncio.sleep(2)
    status = await provision.cmd(
        conn,
        "systemctl is-active twinpanel-agent.service",
        check=False,
    )
    if status.strip() != "active":
        journal = await provision.cmd(
            conn,
            "journalctl -u twinpanel-agent.service -n 30 --no-pager",
            check=False,
        )
        # Preserve the previously working Agent when an upgrade restart fails.
        await provision.cmd(
            conn,
            "if [ -f /opt/twinpanel-agent/agent.py.bak ]; then "
            "cp -f /opt/twinpanel-agent/agent.py.bak "
            "/opt/twinpanel-agent/agent.py; "
            "systemctl restart twinpanel-agent.service || true; fi",
            check=False,
        )
        raise RuntimeError(
            "Agent after restart is not active. "
            + (journal[-1800:] if journal else status)
        )

    pid = await provision.cmd(
        conn,
        "systemctl show twinpanel-agent.service -p MainPID --value",
        check=False,
    )
    return {
        "service": "active",
        "pid": int(pid) if pid.isdigit() else None,
        "agent_path": "/opt/twinpanel-agent/agent.py",
        "backup_path": "/opt/twinpanel-agent/agent.py.bak",
        "dependency_source": dependency_source,
        "resilience_marker": MARKER,
    }


async def _install_or_upgrade_agent_v278(
    conn,
    node_id: int,
    api_base: str,
) -> dict:
    db = SessionLocal()
    try:
        node = db.get(Node, int(node_id))
        if node is not None and node.node_type == NodeType.IRAN:
            return await _install_iran_agent_v278(conn, node_id, api_base)
    finally:
        db.close()

    # Exit behavior remains V70 exactly as captured after importing V66.
    return await _BASE_AGENT_INSTALL(conn, node_id, api_base)


async def install_node_v278(
    payload: provision.InstallIn,
    request: Request,
    db: Session = Depends(get_db),
):
    if payload.node_type != NodeType.IRAN:
        return await _BASE_INSTALL_NODE(payload, request, db)

    # Iran nodes are tunnel/relay-only, preserving the existing authority.
    payload.install_cisco = False
    payload.install_openvpn = False
    payload.install_wireguard = False
    payload.install_l2tp = False
    payload.install_v2ray = False

    by_name = _active_node_by_name(db, payload.name)
    by_ip = _active_node_by_ip(db, payload.host)

    if by_name is not None and by_ip is not None and by_name.id != by_ip.id:
        raise HTTPException(
            status_code=409,
            detail="نام و IP به دو نود متفاوت تعلق دارند؛ ابتدا تعارض را بررسی کنید",
        )

    node = by_name or by_ip
    resumed = node is not None

    if node is not None:
        if (
            str(node.name) != str(payload.name)
            or str(node.public_ip) != str(payload.host)
            or node.node_type != NodeType.IRAN
        ):
            raise HTTPException(
                status_code=409,
                detail="نام یا IP قبلاً برای نود دیگری ثبت شده است",
            )

        # A fully online node with saved access is not a failed create; use the
        # normal node-management actions instead of reprovisioning it.
        if node.status == NodeStatus.ONLINE and _saved_access(db, node.id):
            raise HTTPException(
                status_code=409,
                detail="این نود از قبل فعال است؛ برای تغییرات از مدیریت نود استفاده کنید",
            )

    conn = await provision.ssh_connect(payload)
    stage = "ssh_connected"

    try:
        os_id = await provision.cmd(
            conn,
            ". /etc/os-release && printf '%s' \"$ID\"",
        )
        if os_id not in ("ubuntu", "debian"):
            raise HTTPException(
                status_code=400,
                detail="فعلاً Ubuntu/Debian پشتیبانی می‌شود",
            )

        stage = "ensure_base"
        await provision.ensure_base(conn)

        if node is None:
            stage = "create_node"
            node = Node(
                name=payload.name,
                node_type=NodeType.IRAN,
                country_code="IR",
                public_ip=payload.host,
                agent_url=f"https://{payload.host}:9443",
                status=NodeStatus.OFFLINE,
                capacity_users=payload.capacity_users,
                enable_cisco=False,
                enable_openvpn=False,
                enable_wireguard=False,
                enable_l2tp=False,
                enable_v2ray=False,
            )
            db.add(node)
            db.commit()
            db.refresh(node)
        else:
            stage = "refresh_partial_node"
            node.country_code = "IR"
            node.capacity_users = payload.capacity_users
            node.agent_url = f"https://{payload.host}:9443"
            db.commit()
            db.refresh(node)

        # Save managed SSH access before Agent/network-dependent work. A later
        # failure is therefore safely resumable from the Node management page.
        stage = "save_access"
        access = await provision._ensure_node_key_on_remote(
            conn,
            db,
            node,
            payload.port,
            payload.username,
        )

        stage = "install_agent"
        agent = await _install_or_upgrade_agent_v278(
            conn,
            node.id,
            provision.api_base_url(db, request),
        )

        stage = "install_tunnel_fabric"
        try:
            fabric = await provision._install_tunnel_fabric_base(conn, node)
        except Exception as exc:
            fabric = {
                "ok": False,
                "service": "failed",
                "error": str(exc)[:1800],
            }

        stage = "subscription_sync"
        subscription_sync = {
            "ok": True,
            "skipped": True,
            "reason": "not_run",
        }
        try:
            from .routers.account_delivery import sync_installed_node_to_subscriptions

            subscription_sync = await sync_installed_node_to_subscriptions(db, node)
        except Exception as exc:
            db.rollback()
            subscription_sync = {
                "ok": False,
                "error": str(exc)[:1200],
            }

        return {
            "ok": bool(fabric.get("ok")),
            "node_id": node.id,
            "node_name": node.name,
            "status": "installed" if fabric.get("ok") else "partial",
            "protocols": {},
            "failed_protocols": [] if fabric.get("ok") else ["tunnel_fabric"],
            "one_time_secrets": {},
            "agent": agent,
            "quota": {
                "ok": True,
                "skipped": True,
                "reason": "iran_tunnel_only",
            },
            "subscription_sync": subscription_sync,
            "fabric": fabric,
            "access_saved": bool(access),
            "resumed": resumed,
            "resilience_marker": MARKER,
            "message": (
                "نود ایران با موفقیت آماده شد"
                if fabric.get("ok")
                else "نود و Agent آماده شدند؛ Tunnel Fabric نیاز به بررسی دارد"
            ),
        }

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        if node is not None:
            try:
                current = db.get(Node, int(node.id))
                if current is not None:
                    current.status = NodeStatus.OFFLINE
                    db.commit()
            except Exception:
                db.rollback()

        raise HTTPException(
            status_code=502,
            detail={
                "code": "iran_node_provision_partial",
                "stage": stage,
                "node_id": int(node.id) if node is not None else None,
                "resumable": node is not None,
                "error": str(exc)[:1800],
            },
        ) from exc
    finally:
        conn.close()
        await conn.wait_closed()


def apply_provision_resilience_v278() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    provision._install_or_upgrade_agent = _install_or_upgrade_agent_v278

    replaced = False
    for route in provision.router.routes:
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", "") != "/v1/provision/install":
            continue
        if "POST" not in methods:
            continue

        # FastAPI's request handler captures the Dependant object. Replacing its
        # call preserves the already-built validation/dependency graph while
        # changing only the endpoint implementation.
        route.endpoint = install_node_v278
        if getattr(route, "dependant", None) is not None:
            route.dependant.call = install_node_v278
        replaced = True
        break

    if not replaced:
        raise RuntimeError("provision_install_route_not_found_v278")

    _RUNTIME_APPLIED = True