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

    @staticmethod
    def _signal_process_group(
        process: asyncio.subprocess.Process,
        sig: signal.Signals,
    ) -> None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        except Exception:
            try:
                process.send_signal(sig)
            except ProcessLookupError:
                return

    async def run(
        self,
        command: str,
        check: bool = False,
        timeout: float | None = None,
    ) -> LocalRunResult:
        timeout_value: float | None = None
        if timeout is not None:
            timeout_value = float(timeout)
            if timeout_value <= 0:
                raise ValueError("timeout must be greater than zero")

        process = await asyncio.create_subprocess_shell(
            command,
            executable="/bin/bash",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        communicate_task = asyncio.create_task(process.communicate())
        timed_out = False

        try:
            if timeout_value is None:
                stdout_bytes, stderr_bytes = await communicate_task
            else:
                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        asyncio.shield(communicate_task),
                        timeout=timeout_value,
                    )
                except asyncio.TimeoutError:
                    timed_out = True
                    self._signal_process_group(process, signal.SIGTERM)
                    try:
                        await asyncio.wait_for(process.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        self._signal_process_group(process, signal.SIGKILL)
                        try:
                            await asyncio.wait_for(process.wait(), timeout=1.0)
                        except asyncio.TimeoutError:
                            pass

                    try:
                        stdout_bytes, stderr_bytes = await asyncio.wait_for(
                            asyncio.shield(communicate_task),
                            timeout=1.0,
                        )
                    except asyncio.TimeoutError:
                        communicate_task.cancel()
                        try:
                            await communicate_task
                        except (asyncio.CancelledError, Exception):
                            pass
                        stdout_bytes, stderr_bytes = b"", b""
        except asyncio.CancelledError:
            self._signal_process_group(process, signal.SIGKILL)
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except Exception:
                pass
            if not communicate_task.done():
                communicate_task.cancel()
            try:
                await communicate_task
            except (asyncio.CancelledError, Exception):
                pass
            raise

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        exit_status = int(process.returncode or 0)
        if timed_out:
            exit_status = 124
            timeout_message = f"local command timed out after {timeout_value:g}s"
            stderr_text = (
                f"{stderr_text.rstrip()}\n{timeout_message}".lstrip()
                if stderr_text
                else timeout_message
            )

        result = LocalRunResult(
            exit_status=exit_status,
            stdout=stdout_text,
            stderr=stderr_text,
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
