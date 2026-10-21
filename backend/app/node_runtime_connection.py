from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_

from .models import Node, NodeType


@dataclass(slots=True)
class LocalRunResult:
    exit_status: int
    stdout: str
    stderr: str


class LocalRuntimeConnection:
    """AsyncSSH-compatible command runner for TwinPanel Local Core.

    Protocol provisioning code already uses one small connection surface:
    ``run()``, ``close()`` and ``wait_closed()``.  This adapter preserves that
    contract while executing commands directly on the control server instead
    of requiring the server to SSH into itself.
    """

    async def run(self, command: str, check: bool = False) -> LocalRunResult:
        process = await asyncio.create_subprocess_shell(
            command,
            executable="/bin/bash",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout_bytes, stderr_bytes = await process.communicate()
        except asyncio.CancelledError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            try:
                await process.wait()
            except Exception:
                pass
            raise

        result = LocalRunResult(
            exit_status=int(process.returncode or 0),
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
        )
        if check and result.exit_status != 0:
            message = (result.stderr or result.stdout or "local command failed").strip()
            raise RuntimeError(message)
        return result

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


def is_local_core(node: Node) -> bool:
    return bool(
        getattr(node, "is_mother", False)
        or str(getattr(node, "agent_url", "") or "").strip() == "local://core"
    )


def is_protocol_runtime_node(node: Node) -> bool:
    return is_local_core(node) or node.node_type == NodeType.EXIT


def protocol_runtime_node_clause():
    """SQLAlchemy clause matching remote Exit nodes plus TwinPanel Local Core."""

    return or_(
        Node.node_type == NodeType.EXIT,
        Node.agent_url == "local://core",
    )


async def connect_protocol_runtime(node: Node, db: Any):
    """Return a local executor for Local Core, otherwise the saved SSH path."""

    if is_local_core(node):
        if os.name != "posix" or os.geteuid() != 0:
            raise HTTPException(
                status_code=503,
                detail=(
                    "مدیریت پروتکل روی TwinPanel Local Core نیاز دارد "
                    "Backend با دسترسی root اجرا شود"
                ),
            )
        return LocalRuntimeConnection()

    # Lazy import avoids a module cycle because provision imports shared models
    # and the protocol routers import this connection selector.
    from .routers.provision import ssh_connect_saved

    return await ssh_connect_saved(node, db)
