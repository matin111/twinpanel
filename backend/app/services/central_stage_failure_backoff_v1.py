"""Persistent per-node backoff for repeatedly FAILED heavy central stages.

A completed failing node-wide stage is expensive (several daemon families,
SSH, quota-admission/credential audit). Re-launching it each 30 seconds can
starve the user API and SQL. Never mark a failed stage applied. The /run marker
is ephemeral (clears on reboot), keyed by node and never stores credentials.
Manual verified admin repairs do not depend on this automatic scan.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

FOLDER = Path("/run/twinpanel-central-stage-failures")
COOLDOWN_SECONDS = 600


def _marker(node_id: int) -> Path:
    if type(node_id) is not int or not 1 <= node_id <= 1_000_000:
        raise ValueError("CENTRAL_STAGE_COOLDOWN_INVALID_NODE_ID")
    return FOLDER / f"node-{node_id}.json"


def recently_failed(node_id: int, *, at: float | None = None) -> bool:
    """Return only a status; NEVER convert cooldown into a successful ACK."""
    target = _marker(int(node_id))
    if not target.exists():
        return False
    if target.is_symlink() or target.stat().st_size > 512:
        raise RuntimeError("CENTRAL_STAGE_COOLDOWN_MARKER_INVALID")
    try:
        record = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("CENTRAL_STAGE_COOLDOWN_MARKER_INVALID") from exc
    if not isinstance(record, dict) or record.get("node_id") != int(node_id):
        raise RuntimeError("CENTRAL_STAGE_COOLDOWN_MARKER_INVALID")
    when = record.get("completed_at")
    code = record.get("exit_code")
    if type(when) not in (float, int) or type(code) is not int or code == 0:
        raise RuntimeError("CENTRAL_STAGE_COOLDOWN_MARKER_INVALID")
    now = time.time() if at is None else float(at)
    # Future/invalid timestamps fail closed rather than restart an expensive
    # storm until an administrator inspects the marker.
    if when > now + 60:
        raise RuntimeError("CENTRAL_STAGE_COOLDOWN_CLOCK_INVALID")
    return 0 <= now - when < COOLDOWN_SECONDS


def record_result(node_id: int, exit_code: int, *, at: float | None = None) -> None:
    """Atomic fail/clear, no DB changes or retroactive ACK."""
    target = _marker(int(node_id))
    if type(exit_code) is not int:
        raise ValueError("CENTRAL_STAGE_COOLDOWN_EXIT_INVALID")
    if exit_code == 0:
        if target.is_symlink():
            raise RuntimeError("CENTRAL_STAGE_COOLDOWN_MARKER_INVALID")
        target.unlink(missing_ok=True)
        return
    FOLDER.mkdir(parents=True, exist_ok=True, mode=0o700)
    FOLDER.chmod(0o700)
    if target.is_symlink():
        raise RuntimeError("CENTRAL_STAGE_COOLDOWN_MARKER_INVALID")
    marker = {
        "node_id": int(node_id),
        "completed_at": float(time.time() if at is None else at),
        "exit_code": exit_code,
    }
    tmp = target.with_name(target.name + "." + secrets.token_hex(6) + ".tmp")
    try:
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(marker, out, separators=(",", ":"))
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)
        target.chmod(0o600)
    finally:
        tmp.unlink(missing_ok=True)
