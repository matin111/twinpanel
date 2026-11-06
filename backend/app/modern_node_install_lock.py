"""Per-node cross-process guard for modern protocol installs.

A single TwinPanel mother host may run multiple API workers. A non-blocking
flock ensures only one install/apt sequence per node runs at a time, and is
automatically released on process exit. Existing live VPN services are not
modified by this guard.
"""
from __future__ import annotations

import fcntl
import os
from contextlib import asynccontextmanager
from pathlib import Path

LOCK_DIRECTORY = Path("/run/lock/twinpanel-modern-installs")


class NodeInstallBusy(RuntimeError):
    """A modern protocol install is already running for this node."""


@asynccontextmanager
async def exclusive_node_install(node_id: int):
    node_id = int(node_id)
    if node_id <= 0:
        raise ValueError("node_id must be positive")
    LOCK_DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = LOCK_DIRECTORY / f"node-{node_id}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    locked = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except BlockingIOError as exc:
            raise NodeInstallBusy(f"modern_install_already_running:node={node_id}") from exc
        yield
    finally:
        if locked:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
