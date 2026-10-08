from __future__ import annotations

import asyncio
import base64
import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

import asyncssh
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import (
    Node,
    NodeAccess,
    NodeProtocolConfig,
    NodeStatus,
    Subscription,
    SubscriptionNode,
    Tunnel,
    TunnelPeerState,
    TunnelTransport,
)

router = APIRouter(tags=["nodes"], dependencies=[Depends(require_admin)])


def _controller_ip_fallback() -> str:
    try:
        output = subprocess.check_output(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            text=True,
            timeout=5,
        )
        match = re.search(r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)\b", output)
        if match:
            return f"http://{match.group(1)}"
    except Exception:
        pass
    return ""


def _get_access(db: Session, node_id: int) -> NodeAccess | None:
    return db.query(NodeAccess).filter(NodeAccess.node_id == node_id).first()


async def _saved_ssh(node: Node, access: NodeAccess):
    key_path = Path(access.private_key_path)
    if not key_path.exists():
        raise HTTPException(
            status_code=409,
            detail="کلید SSH ذخیره‌شده این نود پیدا نشد؛ دسترسی SSH را دوباره ثبت کنید.",
        )
    try:
        return await asyncssh.connect(
            node.public_ip,
            port=access.ssh_port,
            username=access.ssh_username,
            client_keys=[str(key_path)],
            known_hosts=None,
            connect_timeout=12,
            login_timeout=12,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"اتصال SSH به نود ناموفق بود: {exc}")


@router.post("/v1/nodes/{node_id}/recover-agent")
async def recover_node_agent(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    node = (
        db.query(Node)
        .filter(Node.id == node_id, Node.retired_at.is_(None))
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if getattr(node, "is_mother", False):
        raise HTTPException(status_code=400, detail="سرور مادر Node Agent راه دور ندارد")

    access = _get_access(db, node_id)
    if not access:
        raise HTTPException(
            status_code=409,
            detail="دسترسی SSH ذخیره نشده است؛ ابتدا «ثبت دسترسی SSH» را انجام دهید.",
        )

    api_base = _controller_ip_fallback()
    if not api_base:
        host = str(request.base_url).split("/", 3)[:3]
        api_base = "/".join(host).rstrip("/")

    conn = await _saved_ssh(node, access)
    try:
        agent_path = "/opt/twinpanel-agent/agent.py"
        exists = await conn.run(f"test -s {shlex.quote(agent_path)}", check=False)
        if exists.exit_status != 0:
            raise HTTPException(
                status_code=409,
                detail="Node Agent روی این سرور پیدا نشد؛ دسترسی/نصب Agent را دوباره انجام دهید.",
            )

        python_code = (
            "from pathlib import Path\n"
            "import re\n"
            f"p=Path({agent_path!r})\n"
            "t=p.read_text()\n"
            f"replacement={'API = ' + repr(api_base)!r}\n"
            "t,n=re.subn(r'^API\\s*=.*$', replacement, t, count=1, flags=re.M)\n"
            "assert n==1, 'API assignment not found'\n"
            "tmp=p.with_suffix('.py.new')\n"
            "tmp.write_text(t)\n"
            "tmp.chmod(0o600)\n"
            "tmp.replace(p)\n"
        )
        encoded = base64.b64encode(python_code.encode()).decode()
        command = (
            "set -e; "
            f"printf '%s' {shlex.quote(encoded)} | base64 -d | python3; "
            f"/opt/twinpanel-agent/venv/bin/python -m py_compile {shlex.quote(agent_path)}; "
            "systemctl daemon-reload; "
            "systemctl enable twinpanel-agent.service >/dev/null 2>&1 || true; "
            "systemctl restart twinpanel-agent.service"
        )
        result = await conn.run(command, check=False, timeout=45)
        if result.exit_status != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise HTTPException(
                status_code=500,
                detail="بازیابی Node Agent ناموفق بود: " + detail[-1200:],
            )

        await asyncio.sleep(4)
        state = await conn.run(
            "systemctl is-active twinpanel-agent.service; "
            "journalctl -u twinpanel-agent.service -n 12 --no-pager",
            check=False,
            timeout=20,
        )
        output = (state.stdout or state.stderr or "").strip()
        if not output.startswith("active"):
            raise HTTPException(
                status_code=500,
                detail="Node Agent بعد از بازیابی فعال نماند: " + output[-1200:],
            )

        db.expire_all()
        node = db.get(Node, node_id)
        return {
            "ok": True,
            "node_id": node_id,
            "api_base": api_base,
            "service": "active",
            "status": getattr(node.status, "value", str(node.status)) if node else "unknown",
            "last_seen_at": node.last_seen_at.isoformat() if node and node.last_seen_at else None,
            "message": "Node Agent بازیابی شد و مسیر API روی IP کنترلر قرار گرفت",
        }
    finally:
        conn.close()
        await conn.wait_closed()


def _table_exists(db: Session, name: str) -> bool:
    return bool(db.execute(text("SELECT to_regclass(:name)"), {"name": f"public.{name}"}).scalar())


@router.post("/v1/nodes/{node_id}/force-retire")
def force_retire_node(node_id: int, db: Session = Depends(get_db)):
    node = (
        db.query(Node)
        .filter(Node.id == node_id, Node.retired_at.is_(None))
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if getattr(node, "is_mother", False):
        raise HTTPException(status_code=409, detail="سرور مادر قابل حذف نیست")

    now = datetime.utcnow()
    original_name = str(node.name)
    tunnel_ids = [
        row[0]
        for row in db.query(Tunnel.id)
        .filter((Tunnel.iran_node_id == node_id) | (Tunnel.exit_node_id == node_id))
        .all()
    ]

    try:
        db.query(Subscription).filter(Subscription.iran_node_id == node_id).update(
            {Subscription.iran_node_id: None}, synchronize_session=False
        )
        db.query(Subscription).filter(Subscription.exit_node_id == node_id).update(
            {Subscription.exit_node_id: None}, synchronize_session=False
        )
        db.query(SubscriptionNode).filter(SubscriptionNode.node_id == node_id).delete(
            synchronize_session=False
        )
        db.query(NodeProtocolConfig).filter(NodeProtocolConfig.node_id == node_id).delete(
            synchronize_session=False
        )

        if tunnel_ids:
            db.query(TunnelPeerState).filter(TunnelPeerState.tunnel_id.in_(tunnel_ids)).delete(
                synchronize_session=False
            )
            db.query(TunnelTransport).filter(TunnelTransport.tunnel_id.in_(tunnel_ids)).delete(
                synchronize_session=False
            )
            db.query(Tunnel).filter(Tunnel.id.in_(tunnel_ids)).delete(
                synchronize_session=False
            )

        db.query(TunnelPeerState).filter(TunnelPeerState.node_id == node_id).delete(
            synchronize_session=False
        )

        for table_name in ("quota_cursors", "quota_node_commands", "quota_agent_identities"):
            if _table_exists(db, table_name):
                db.execute(
                    text(f"DELETE FROM {table_name} WHERE node_id = :node_id"),
                    {"node_id": node_id},
                )

        db.query(NodeAccess).filter(NodeAccess.node_id == node_id).delete(synchronize_session=False)

        node.retired_at = now
        node.status = NodeStatus.OFFLINE
        node.current_users = 0
        node.enable_cisco = False
        node.enable_openvpn = False
        node.enable_wireguard = False
        node.enable_l2tp = False
        node.enable_v2ray = False
        node.public_domain = None
        node.agent_url = f"retired://node/{node_id}"

        suffix = f" [retired-{node_id}]"
        node.name = original_name[: max(1, 120 - len(suffix))] + suffix

        db.commit()
        return {
            "ok": True,
            "node_id": node_id,
            "retired": True,
            "removed_tunnels": len(tunnel_ids),
            "warning": "Remote runtime cleanup was skipped; the node was removed from active control-plane state.",
            "message": "نود آفلاین از پنل حذف شد",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"حذف اجباری نود ناموفق بود: {str(exc)[:1200]}")
