from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeProtocolConfig, NodeStatus, Subscription, SubscriptionNode, Tunnel, TunnelPeerState, TunnelTransport, TunnelStatus, CleanupJob
from ..mother_access import admin_can_use_mother
from ..schemas import NodeCreate, NodeHeartbeatIn, NodeOut, NodeUpdate

router = APIRouter(prefix="/v1/nodes", tags=["nodes"])


STALE_AFTER_SECONDS = 90


def _refresh_stale_status(node: Node, now: datetime) -> bool:
    # TWINPANEL_MOTHER_LOCAL_STATUS_V1
    #
    # Mother is the local VPN core itself.
    # It does not use the remote Node Agent heartbeat.
    # Protocol/service health is checked separately.
    if getattr(node, "is_mother", False):
        if node.status == NodeStatus.MAINTENANCE:
            return False

        if node.status != NodeStatus.ONLINE:
            node.status = NodeStatus.ONLINE
            return True

        return False

    if node.status == NodeStatus.MAINTENANCE:
        return False
    if node.last_seen_at is None:
        if node.status != NodeStatus.OFFLINE:
            node.status = NodeStatus.OFFLINE
            return True
        return False
    age = (now - node.last_seen_at).total_seconds()
    desired = NodeStatus.ONLINE if age <= STALE_AFTER_SECONDS else NodeStatus.OFFLINE
    if node.status != desired:
        node.status = desired
        return True
    return False


@router.get("", response_model=list[NodeOut], dependencies=[Depends(require_admin)])
def list_nodes(db: Session = Depends(get_db)):
    nodes = db.query(Node).filter(Node.retired_at.is_(None)).order_by(Node.id.desc()).all()
    now = datetime.utcnow()
    changed = any(_refresh_stale_status(node, now) for node in nodes)
    if changed:
        db.commit()

    # TWINPANEL_MOTHER_ADMIN_VISIBILITY_V100
    # Keep the Mother row and its local runtime intact. The admin access
    # setting controls whether it is exposed through the admin node discovery
    # API used by node tables and selectors.
    if not admin_can_use_mother(db):
        nodes = [
            node
            for node in nodes
            if not getattr(node, "is_mother", False)
        ]

    return nodes


@router.get("/{node_id}/health", dependencies=[Depends(require_admin)])
def node_health(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")

    now = datetime.utcnow()
    changed = _refresh_stale_status(node, now)
    if changed:
        db.commit()
        db.refresh(node)

    age_seconds = None
    if node.last_seen_at is not None:
        age_seconds = max(0, int((now - node.last_seen_at).total_seconds()))

    protocols = {
        "cisco": node.enable_cisco,
        "openvpn": node.enable_openvpn,
        "wireguard": node.enable_wireguard,
        "l2tp": node.enable_l2tp,
        "v2ray": node.enable_v2ray,
    }

    return {
        "ok": node.status == NodeStatus.ONLINE,
        "node_id": node.id,
        "status": node.status.value,
        "last_seen_at": node.last_seen_at.isoformat() if node.last_seen_at else None,
        "heartbeat_age_seconds": age_seconds,
        "current_users": node.current_users,
        "capacity_users": node.capacity_users,
        "protocols": protocols,
        "message": (
            "Node Agent آنلاین است"
            if node.status == NodeStatus.ONLINE
            else "Heartbeat نود دریافت نمی‌شود"
            if node.status != NodeStatus.MAINTENANCE
            else "نود در حالت نگهداری است"
        ),
    }


@router.get("/{node_id}/protocols", dependencies=[Depends(require_admin)])
def node_protocols(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    items = db.query(NodeProtocolConfig).filter(NodeProtocolConfig.node_id == node_id).order_by(NodeProtocolConfig.protocol.asc()).all()
    return [{"protocol":x.protocol,"port":x.port,"port_text":x.port_text,"transport":x.transport,"service_name":x.service_name,"status":x.status,"last_error":x.last_error,"checked_at":x.checked_at.isoformat() if x.checked_at else None} for x in items]


@router.post("", response_model=NodeOut, dependencies=[Depends(require_admin)])
def create_node(payload: NodeCreate, db: Session = Depends(get_db)):
    existing = db.query(Node).filter(Node.retired_at.is_(None)).filter(Node.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="نام سرور تکراری است")

    # TWINPANEL_ACTIVE_NODE_IP_GUARD_V1
    public_ip = str(payload.public_ip or "").strip()

    existing_ip = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.public_ip == public_ip,
        )
        .first()
    )

    if existing_ip:
        raise HTTPException(
            status_code=409,
            detail=(
                "این IP قبلاً برای یک سرور فعال ثبت شده است: "
                f"{existing_ip.name} (ID {existing_ip.id})"
            ),
        )

    data = payload.model_dump()
    data["public_ip"] = public_ip

    if not data.get("agent_url"):
        data["agent_url"] = f"https://{public_ip}:9443"

    node = Node(**data)
    db.add(node)
    db.flush()

    # TWINPANEL_NEW_NODE_AUTO_ALL_SUBSCRIPTIONS_V1
    #
    # Every newly created Node immediately belongs to every
    # existing subscription. This also preserves compatibility
    # with quota/enforcement code that still uses SubscriptionNode.
    subscription_ids = [
        int(row[0])
        for row in (
            db.query(Subscription.id)
            .order_by(Subscription.id.asc())
            .all()
        )
    ]

    for subscription_id in subscription_ids:
        db.add(
            SubscriptionNode(
                subscription_id=subscription_id,
                node_id=node.id,
            )
        )

    db.commit()
    db.refresh(node)
    return node


@router.patch("/{node_id}", response_model=NodeOut, dependencies=[Depends(require_admin)])
def update_node(node_id: int, payload: NodeUpdate, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")

    data = payload.model_dump(
        exclude_unset=True
    )

    # TWINPANEL_ACTIVE_NODE_IP_GUARD_V1
    if "public_ip" in data:
        new_ip = str(
            data.get("public_ip")
            or ""
        ).strip()

        duplicate = (
            db.query(Node)
            .filter(
                Node.retired_at.is_(None),
                Node.public_ip == new_ip,
                Node.id != node_id,
            )
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=(
                    "این IP قبلاً برای یک سرور فعال "
                    "ثبت شده است: "
                    f"{duplicate.name} "
                    f"(ID {duplicate.id})"
                ),
            )

        data["public_ip"] = new_ip

    for key, value in data.items():
        setattr(node, key, value)

    db.commit()
    db.refresh(node)
    return node


@router.post("/{node_id}/maintenance", response_model=NodeOut, dependencies=[Depends(require_admin)])
def toggle_maintenance(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")

    node.status = NodeStatus.OFFLINE if node.status == NodeStatus.MAINTENANCE else NodeStatus.MAINTENANCE
    db.commit()
    db.refresh(node)
    return node



# TWINPANEL_NODE_QUOTA_PKI_CLEANUP_V1
def _cleanup_node_quota_pki(
    node_id: int,
) -> list[str]:
    """
    Remove only controller-side quota PKI files
    belonging to this Node.

    CA files and other Node identities are untouched.
    """
    base = Path(
        "/root/.vpnshop/quota-pki"
    )

    removed: list[str] = []

    for suffix in (
        ".crt",
        ".csr",
        ".ext",
        ".key",
    ):
        target = (
            base
            / f"node-{int(node_id)}{suffix}"
        )

        if not target.exists():
            continue

        target.unlink(
            missing_ok=True
        )

        removed.append(
            str(target)
        )

    return removed


@router.delete("/{node_id}", dependencies=[Depends(require_admin)])
async def delete_node(
    node_id: int,
    db: Session = Depends(get_db),
):
    """
    TWINPANEL_NODE_LIFECYCLE_DELETE_V1

    Normal deletion is strict:
      1. disable related tunnels
      2. clean their runtime
      3. clean this node runtime
      4. remove mutable DB objects
      5. retire the node

    Historical quota usage remains append-only.
    """

    from ..lifecycle_cleanup import (
        cleanup_node_runtime,
        cleanup_tunnel_runtime,
        related_tunnel_ids_for_node,
    )

    node = (
        db.query(Node)
        .filter(
            Node.id == node_id,
            Node.retired_at.is_(None),
        )
        .first()
    )

    if not node:
        raise HTTPException(
            status_code=404,
            detail="سرور پیدا نشد",
        )

    if getattr(node, "is_mother", False):
        raise HTTPException(
            status_code=409,
            detail="سرور مادر قابل حذف نیست",
        )

    original_name = str(node.name)
    now = datetime.utcnow()

    tunnel_ids = (
        related_tunnel_ids_for_node(
            db,
            node_id,
        )
    )

    # TWINPANEL_CLEANUP_JOB_NODE_V1
    #
    # Persist cleanup jobs BEFORE touching remote runtime.
    # This guarantees that failures are always traceable.
    node_cleanup_job = CleanupJob(
        target_type="node",
        target_id=int(node_id),
        action="remove_runtime",
        status="running",
    )

    db.add(node_cleanup_job)
    db.flush()

    node_cleanup_job_id = int(
        node_cleanup_job.id
    )

    tunnel_cleanup_job_ids = {}

    for cleanup_tunnel_id in tunnel_ids:
        cleanup_job = CleanupJob(
            target_type="tunnel",
            target_id=int(cleanup_tunnel_id),
            action="remove_runtime",
            status="running",
        )

        db.add(cleanup_job)
        db.flush()

        tunnel_cleanup_job_ids[
            int(cleanup_tunnel_id)
        ] = int(cleanup_job.id)

    db.commit()

    # -------------------------------------------------
    # Phase 1: remove every affected Tunnel from
    # desired-state BEFORE remote cleanup.
    # -------------------------------------------------

    related_tunnels = []

    for tunnel_id in tunnel_ids:
        tunnel = db.get(
            Tunnel,
            int(tunnel_id),
        )

        if not tunnel:
            continue

        tunnel.is_active = False
        tunnel.status = TunnelStatus.OFFLINE
        tunnel.latency_ms = None

        related_tunnels.append(
            tunnel
        )

    db.commit()

    # -------------------------------------------------
    # Phase 2: strict remote cleanup.
    #
    # If this fails the Node is NOT retired and
    # the Tunnel DB records are NOT deleted.
    # They remain disabled and deletion can be retried.
    # -------------------------------------------------

    tunnel_cleanup_results = []

    try:
        for tunnel in related_tunnels:
            result = await cleanup_tunnel_runtime(
                tunnel,
                db,
            )

            tunnel_cleanup_results.append(
                result
            )

        node_cleanup = await cleanup_node_runtime(
            node,
            db,
        )

    except Exception as exc:
        error_text = str(exc)[:2000]
        finished_at = datetime.utcnow()

        job = db.get(
            CleanupJob,
            node_cleanup_job_id,
        )

        if job:
            job.status = "failed"
            job.error = error_text
            job.finished_at = finished_at

        for job_id in tunnel_cleanup_job_ids.values():
            job = db.get(
                CleanupJob,
                int(job_id),
            )

            if job:
                job.status = "failed"
                job.error = error_text
                job.finished_at = finished_at

        db.commit()

        raise HTTPException(
            status_code=409,
            detail=(
                "پاک‌سازی کامل سرور انجام نشد؛ "
                "سرور از پنل حذف نشد. "
                "تونل‌های مرتبط برای جلوگیری از بازسازی "
                "خودکار غیرفعال شدند. "
                f"جزئیات: {str(exc)[:1800]}"
            ),
        )

    key_path = (
        node_cleanup.get(
            "controller_key_path"
        )
        if isinstance(
            node_cleanup,
            dict,
        )
        else None
    )

    try:
        # -------------------------------------------------
        # Detach subscriptions without deleting history.
        # -------------------------------------------------

        db.query(Subscription).filter(
            Subscription.iran_node_id == node_id
        ).update(
            {
                Subscription.iran_node_id:
                None
            },
            synchronize_session=False,
        )

        db.query(Subscription).filter(
            Subscription.exit_node_id == node_id
        ).update(
            {
                Subscription.exit_node_id:
                None
            },
            synchronize_session=False,
        )

        # -------------------------------------------------
        # Remove active membership/configuration.
        # -------------------------------------------------

        db.query(SubscriptionNode).filter(
            SubscriptionNode.node_id == node_id
        ).delete(
            synchronize_session=False
        )

        db.query(NodeProtocolConfig).filter(
            NodeProtocolConfig.node_id == node_id
        ).delete(
            synchronize_session=False
        )

        # -------------------------------------------------
        # Remove tunnel DB state ONLY AFTER remote cleanup.
        # -------------------------------------------------

        if tunnel_ids:
            db.query(TunnelPeerState).filter(
                TunnelPeerState.tunnel_id.in_(
                    tunnel_ids
                )
            ).delete(
                synchronize_session=False
            )

            db.query(TunnelTransport).filter(
                TunnelTransport.tunnel_id.in_(
                    tunnel_ids
                )
            ).delete(
                synchronize_session=False
            )

            db.query(Tunnel).filter(
                Tunnel.id.in_(
                    tunnel_ids
                )
            ).delete(
                synchronize_session=False
            )

        db.query(TunnelPeerState).filter(
            TunnelPeerState.node_id == node_id
        ).delete(
            synchronize_session=False
        )

        # -------------------------------------------------
        # Mutable quota/control-plane objects.
        # Historical usage tables remain untouched.
        # -------------------------------------------------

        params = {
            "node_id": node_id
        }

        db.execute(
            text("""
                DELETE FROM quota_cursors
                WHERE node_id = :node_id
            """),
            params,
        )

        db.execute(
            text("""
                DELETE FROM quota_node_commands
                WHERE node_id = :node_id
            """),
            params,
        )

        db.execute(
            text("""
                DELETE FROM quota_agent_identities
                WHERE node_id = :node_id
            """),
            params,
        )

        # -------------------------------------------------
        # Optional / legacy outbounds.
        # -------------------------------------------------

        outbounds_exists = bool(
            db.execute(
                text(
                    "SELECT to_regclass("
                    "'public.outbounds'"
                    ")"
                )
            ).scalar()
        )

        if outbounds_exists:
            db.execute(
                text("""
                    DELETE FROM outbounds
                    WHERE iran_node_id = :node_id
                """),
                params,
            )

            db.execute(
                text("""
                    UPDATE outbounds
                    SET exit_node_id = NULL
                    WHERE exit_node_id = :node_id
                """),
                params,
            )

        # -------------------------------------------------
        # Remove retired Node from mutable credential payloads.
        # -------------------------------------------------

        delivery_cleanup = {
            "removed_items": 0
        }

        try:
            from .account_delivery import (
                remove_node_from_delivery_credentials,
            )

            delivery_cleanup = (
                remove_node_from_delivery_credentials(
                    db,
                    node_id,
                )
            )

        except Exception:
            # Runtime cleanup and retirement must not be
            # rolled back merely because an old credential
            # payload cannot be rewritten.
            delivery_cleanup = {
                "removed_items": 0
            }

        # -------------------------------------------------
        # NodeAccess is deliberately LAST.
        # Remote cleanup required this key.
        # -------------------------------------------------

        db.execute(
            text("""
                DELETE FROM node_access
                WHERE node_id = :node_id
            """),
            params,
        )

        # -------------------------------------------------
        # RETIRE — preserve historical identity.
        # -------------------------------------------------

        node.retired_at = now
        node.status = NodeStatus.OFFLINE
        node.current_users = 0

        node.enable_cisco = False
        node.enable_openvpn = False
        node.enable_wireguard = False
        node.enable_l2tp = False
        node.enable_v2ray = False

        node.agent_url = (
            f"retired://node/{node_id}"
        )

        node.public_domain = None

        suffix = (
            f" [retired-{node_id}]"
        )

        max_original = max(
            1,
            120 - len(suffix),
        )

        node.name = (
            original_name[:max_original]
            + suffix
        )

        finished_at = datetime.utcnow()

        job = db.get(
            CleanupJob,
            node_cleanup_job_id,
        )

        if job:
            job.status = "completed"
            job.error = None
            job.finished_at = finished_at

        for job_id in tunnel_cleanup_job_ids.values():
            job = db.get(
                CleanupJob,
                int(job_id),
            )

            if job:
                job.status = "completed"
                job.error = None
                job.finished_at = finished_at

        db.commit()

    except Exception as exc:
        db.rollback()

        error_text = (
            "Runtime پاک شد اما پاک‌سازی دیتابیس شکست خورد: "
            + str(exc)[:1800]
        )

        finished_at = datetime.utcnow()

        try:
            job = db.get(
                CleanupJob,
                node_cleanup_job_id,
            )

            if job:
                job.status = "failed"
                job.error = error_text
                job.finished_at = finished_at

            for job_id in tunnel_cleanup_job_ids.values():
                job = db.get(
                    CleanupJob,
                    int(job_id),
                )

                if job:
                    job.status = "failed"
                    job.error = error_text
                    job.finished_at = finished_at

            db.commit()

        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "Runtime سرور پاک شد اما "
                "پاک‌سازی دیتابیس کامل نشد. "
                "حذف را دوباره اجرا کنید. "
                f"جزئیات: {str(exc)[:1200]}"
            ),
        )

    # TWINPANEL_NODE_QUOTA_PKI_POST_COMMIT_V1
    # DB retirement has already committed successfully.
    # Controller-side quota PKI can now be removed safely.
    quota_pki_removed = []
    quota_pki_cleanup_error = None

    try:
        quota_pki_removed = (
            _cleanup_node_quota_pki(
                node_id
            )
        )

    except Exception as exc:
        # Node is already retired at this point.
        # Do not report the whole deletion as failed merely
        # because local PKI file cleanup had a filesystem error.
        quota_pki_cleanup_error = (
            str(exc)[:1000]
        )

    # Local controller private key is no longer needed.
    if key_path:
        try:
            Path(
                key_path
            ).unlink(
                missing_ok=True
            )

        except Exception:
            pass

    return {
        "ok": True,
        "deleted_node_id": node_id,
        "retired": True,
        "quota_pki_removed": quota_pki_removed,
        "quota_pki_cleanup_error": quota_pki_cleanup_error,
        "removed_tunnels": len(
            tunnel_ids
        ),
        "removed_delivery_items": int(
            delivery_cleanup.get(
                "removed_items",
                0,
            )
        ),
        "runtime_cleanup": {
            "node": node_cleanup,
            "tunnels": tunnel_cleanup_results,
        },
        "message": (
            "سرور و Runtimeهای مدیریت‌شده آن حذف شدند"
        ),
    }


@router.post("/{node_id}/heartbeat")
def heartbeat(
    node_id: int,
    payload: NodeHeartbeatIn,
    x_node_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if x_node_secret != settings.node_agent_shared_secret:
        raise HTTPException(status_code=401, detail="Invalid node secret")

    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    if node.status != NodeStatus.MAINTENANCE:
        node.status = NodeStatus.ONLINE

    node.current_users = payload.current_users
    node.last_seen_at = datetime.utcnow()

    node.enable_cisco = bool(payload.protocols.get("cisco", False))
    node.enable_openvpn = bool(payload.protocols.get("openvpn", False))
    node.enable_wireguard = bool(payload.protocols.get("wireguard", False))
    node.enable_l2tp = bool(payload.protocols.get("l2tp", False))
    node.enable_v2ray = bool(payload.protocols.get("v2ray", False))

    db.commit()
    return {"ok": True}



# VPNShop_MOTHER_NODE_V1_START

from fastapi import Depends as _MotherDepends
from fastapi import HTTPException as _MotherHTTPException
from sqlalchemy.orm import Session as _MotherSession

from ..database import get_db as _mother_get_db
from ..deps import require_admin as _mother_require_admin


@router.post(
    "/mother/bootstrap",
    dependencies=[
        _MotherDepends(_mother_require_admin)
    ],
)
def bootstrap_mother_node_v1(
    db: _MotherSession =
        _MotherDepends(_mother_get_db),
):

    import os
    import re
    import socket
    import subprocess

    from datetime import datetime
    from pathlib import Path

    from ..models import (
        Node,
        NodeAccess,
        NodeStatus,
        NodeType,
    )


    # --------------------------------------------------------
    # Public service address
    # --------------------------------------------------------

    try:

        route=subprocess.check_output(
            [
                "ip",
                "-4",
                "route",
                "get",
                "1.1.1.1",
            ],
            text=True,
            timeout=5,
        )

        match=re.search(
            r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)",
            route,
        )

        if not match:
            raise RuntimeError(
                "public source IP not found"
            )

        service_ip=match.group(1)

    except Exception as exc:

        raise _MotherHTTPException(
            status_code=500,
            detail=(
                "IP عمومی سرور مادر شناسایی نشد: "
                + str(exc)
            ),
        )


    hostname=socket.gethostname().strip() or "core"

    now=datetime.utcnow()


    # --------------------------------------------------------
    # Core protocols already running on this VPS
    # --------------------------------------------------------

    protocol_state={}

    try:

        from .admin import _core_protocol_status

        for key in (
            "cisco",
            "openvpn",
            "wireguard",
            "l2tp",
            "v2ray",
        ):

            try:
                protocol_state[key]=(
                    _core_protocol_status(key)
                )
            except Exception:
                protocol_state[key]={}

    except Exception:
        protocol_state={}


    def protocol_ready(key: str) -> bool:

        item=protocol_state.get(key) or {}

        return bool(
            item.get("ok")
            or item.get("installed")
        )


    # --------------------------------------------------------
    # Find/Create special Mother node
    #
    # public_ip = loopback for internal SSH management
    # public_domain = actual client-facing address
    # --------------------------------------------------------

    node=(
        db.query(Node).filter(Node.retired_at.is_(None))
        .filter(
            Node.agent_url == "local://core"
        )
        .first()
    )


    if not node:

        name="سرور مادر"

        if (
            db.query(Node).filter(Node.retired_at.is_(None))
            .filter(Node.name == name)
            .first()
        ):
            name=f"سرور مادر · {hostname}"

        node=Node(
            name=name,

            # Compatibility only:
            # Mother is NOT shown as Iran in UI.
            node_type=NodeType.IRAN,

            country_code="CORE",

            # Local management
            public_ip="127.0.0.1",

            # VPN clients receive this address
            public_domain=service_ip,

            agent_url="local://core",

            status=NodeStatus.ONLINE,

            current_users=0,
            capacity_users=5000,

            last_seen_at=now,
        )

        db.add(node)
        db.flush()


    node.public_ip="127.0.0.1"
    node.public_domain=service_ip
    node.agent_url="local://core"
    node.status=NodeStatus.ONLINE
    node.last_seen_at=now

    node.enable_cisco=protocol_ready("cisco")
    node.enable_openvpn=protocol_ready("openvpn")
    node.enable_wireguard=protocol_ready(
        "wireguard"
    )
    node.enable_l2tp=protocol_ready("l2tp")
    node.enable_v2ray=protocol_ready("v2ray")


    # --------------------------------------------------------
    # Secure local SSH key
    #
    # Account provisioning already uses NodeAccess +
    # ssh_connect_saved(). Reuse that engine.
    # --------------------------------------------------------

    key_dir=Path(
        "/root/.vpnshop/core-access"
    )

    key_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    os.chmod(key_dir,0o700)


    private_key=key_dir/"mother_ed25519"
    public_key=key_dir/"mother_ed25519.pub"


    if not private_key.exists():

        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(private_key),
            ],
            check=True,
            timeout=15,
        )


    os.chmod(private_key,0o600)


    ssh_dir=Path("/root/.ssh")

    ssh_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    os.chmod(ssh_dir,0o700)


    authorized_keys=(
        ssh_dir/"authorized_keys"
    )

    public_line=(
        public_key
        .read_text(encoding="utf-8")
        .strip()
    )

    existing=""

    if authorized_keys.exists():
        existing=authorized_keys.read_text(
            encoding="utf-8"
        )

    if public_line not in existing.splitlines():

        with authorized_keys.open(
            "a",
            encoding="utf-8",
        ) as f:

            if existing and not existing.endswith("\n"):
                f.write("\n")

            f.write(public_line+"\n")


    os.chmod(
        authorized_keys,
        0o600,
    )


    fingerprint=""

    try:

        fp=subprocess.check_output(
            [
                "ssh-keygen",
                "-lf",
                str(public_key),
            ],
            text=True,
            timeout=5,
        ).split()

        if len(fp)>1:
            fingerprint=fp[1]

    except Exception:
        fingerprint=""


    access=(
        db.query(NodeAccess)
        .filter(
            NodeAccess.node_id == node.id
        )
        .first()
    )


    if not access:

        access=NodeAccess(
            node_id=node.id,
            ssh_port=22,
            ssh_username="root",
            private_key_path=str(
                private_key
            ),
            public_key_fingerprint=(
                fingerprint or None
            ),
        )

        db.add(access)

    else:

        access.ssh_port=22
        access.ssh_username="root"
        access.private_key_path=str(
            private_key
        )
        access.public_key_fingerprint=(
            fingerprint or None
        )
        access.updated_at=now


    # --------------------------------------------------------
    # Verify local provisioning path BEFORE commit
    # --------------------------------------------------------

    check=subprocess.run(
        [
            "ssh",

            "-i",
            str(private_key),

            "-p",
            "22",

            "-o",
            "BatchMode=yes",

            "-o",
            "IdentitiesOnly=yes",

            "-o",
            "ConnectTimeout=5",

            "-o",
            "StrictHostKeyChecking=no",

            "-o",
            "UserKnownHostsFile=/dev/null",

            "root@127.0.0.1",

            "true",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )


    if check.returncode != 0:

        db.rollback()

        raise _MotherHTTPException(
            status_code=500,
            detail=(
                "دسترسی داخلی سرور مادر آماده نشد: "
                + check.stderr.strip()[-500:]
            ),
        )


    db.commit()
    db.refresh(node)


    return {
        "id":node.id,
        "name":node.name,

        "node_type":node.node_type.value,

        "country_code":node.country_code,

        "public_ip":node.public_ip,
        "public_domain":node.public_domain,

        "agent_url":node.agent_url,

        "status":node.status.value,

        "current_users":node.current_users,
        "capacity_users":node.capacity_users,

        "last_seen_at":(
            node.last_seen_at.isoformat()
            if node.last_seen_at
            else None
        ),

        "enable_cisco":node.enable_cisco,
        "enable_openvpn":node.enable_openvpn,
        "enable_wireguard":
            node.enable_wireguard,
        "enable_l2tp":node.enable_l2tp,
        "enable_v2ray":node.enable_v2ray,

        "is_mother":True,

        "service_host":service_ip,
        "access_ready":True,

        "protocols":protocol_state,
    }


# VPNShop_MOTHER_NODE_V1_END

