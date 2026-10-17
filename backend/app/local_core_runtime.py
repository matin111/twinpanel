from __future__ import annotations

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .models import Node, NodeStatus, NodeType


LOCAL_AGENT_URL = "local://core"
LOCAL_NODE_NAME = "TwinPanel Local Core"


@dataclass(slots=True)
class LocalCommandResult:
    exit_status: int
    stdout: str
    stderr: str


class LocalShellConnection:
    """asyncssh-compatible subset for commands executed on this server."""

    async def run(self, command: str, check: bool = False) -> LocalCommandResult:
        process = await asyncio.create_subprocess_shell(
            command,
            executable="/bin/bash",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_raw, stderr_raw = await process.communicate()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise

        stdout = stdout_raw.decode("utf-8", errors="replace")
        stderr = stderr_raw.decode("utf-8", errors="replace")
        result = LocalCommandResult(
            exit_status=int(process.returncode or 0),
            stdout=stdout,
            stderr=stderr,
        )

        if check and result.exit_status != 0:
            message = (stderr or stdout).strip() or f"command exited {result.exit_status}"
            raise RuntimeError(message)

        return result

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


def _valid_ipv4(value: str) -> bool:
    parts = str(value or "").strip().split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def detect_local_public_ipv4() -> str:
    configured = str(os.getenv("TWINPANEL_LOCAL_PUBLIC_IP", "")).strip()
    if _valid_ipv4(configured):
        return configured

    fallback = str(getattr(settings, "public_api_fallback", "") or "").strip()
    if fallback:
        parsed = urlparse(fallback if "://" in fallback else f"http://{fallback}")
        host = str(parsed.hostname or "").strip()
        if _valid_ipv4(host) and not host.startswith("127."):
            return host

    try:
        process = subprocess.run(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
        match = re.search(r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)\b", process.stdout or "")
        if match and _valid_ipv4(match.group(1)):
            return match.group(1)
    except Exception:
        pass

    return "127.0.0.1"


def _available_local_name(db: Session) -> str:
    existing = db.query(Node).filter(Node.name == LOCAL_NODE_NAME).first()
    if existing is None or getattr(existing, "is_mother", False):
        return LOCAL_NODE_NAME

    suffix = 2
    while db.query(Node).filter(Node.name == f"{LOCAL_NODE_NAME} {suffix}").first() is not None:
        suffix += 1
    return f"{LOCAL_NODE_NAME} {suffix}"


def _assign_sqlite_test_id(db: Session, node: Node) -> None:
    bind = db.get_bind()
    if bind is None or bind.dialect.name != "sqlite":
        return
    current = db.query(func.max(Node.id)).scalar()
    node.id = int(current or 0) + 1


def ensure_local_core_node(db: Session) -> Node:
    node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.agent_url == LOCAL_AGENT_URL,
        )
        .order_by(Node.id.asc())
        .first()
    )

    detected_ip = detect_local_public_ipv4()
    now = datetime.utcnow()

    if node is None:
        node = Node(
            name=_available_local_name(db),
            node_type=NodeType.EXIT,
            country_code=str(os.getenv("TWINPANEL_LOCAL_COUNTRY_CODE", "XX") or "XX")[:8],
            public_ip=detected_ip,
            agent_url=LOCAL_AGENT_URL,
            status=NodeStatus.ONLINE,
            show_to_users=True,
            capacity_users=1000,
            current_users=0,
            last_seen_at=now,
        )
        _assign_sqlite_test_id(db, node)
        db.add(node)
        db.commit()
        db.refresh(node)
        return node

    changed = False
    if node.status != NodeStatus.ONLINE:
        node.status = NodeStatus.ONLINE
        changed = True
    if node.node_type != NodeType.EXIT:
        node.node_type = NodeType.EXIT
        changed = True
    if not str(node.public_ip or "").strip() or str(node.public_ip).startswith("127."):
        node.public_ip = detected_ip
        changed = True
    node.last_seen_at = now
    changed = True

    if changed:
        db.commit()
        db.refresh(node)

    return node


def managed_protocol_nodes(db: Session) -> list[Node]:
    local = ensure_local_core_node(db)
    remote = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
            Node.agent_url != LOCAL_AGENT_URL,
        )
        .order_by(Node.id.asc())
        .all()
    )
    return [local, *remote]


async def connection_for_node(node: Node, db: Session):
    if getattr(node, "is_mother", False) or str(getattr(node, "agent_url", "") or "") == LOCAL_AGENT_URL:
        return LocalShellConnection()

    from .routers.provision import ssh_connect_saved

    return await ssh_connect_saved(node, db)
