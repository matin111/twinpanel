from __future__ import annotations

from typing import Any

from . import xray_modern_runtime
from .routers import provision


# Xray 26.x infers config format from the file name. A temporary path ending
# in `.twinpanel-modern` is therefore rejected even when the file contains
# valid JSON. Keep the legacy path only for stale-file cleanup and use an
# explicit `.json` suffix for every new transactional candidate config.
LEGACY_TEMP_CONFIG = "/usr/local/etc/xray/config.json.twinpanel-modern"
JSON_TEMP_CONFIG = "/usr/local/etc/xray/config.twinpanel-modern.json"

_original_ensure_modern_xray = xray_modern_runtime._ensure_modern_xray
_original_merge_clients_script = xray_modern_runtime._merge_clients_script
_runtime_applied = False


class _JsonTempPathConnection:
    """
    Narrow connection proxy used only while Modern Xray is reconciled.

    The production baseline keeps the original V2 implementation intact. Its
    shell commands still contain the historical temporary path, so this proxy
    rewrites only that exact path before a command reaches the Exit node. No
    other SSH command or provisioning behavior is changed.
    """

    def __init__(self, conn: Any):
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    async def run(self, command: str, *args: Any, **kwargs: Any):
        if isinstance(command, str):
            command = command.replace(
                LEGACY_TEMP_CONFIG,
                JSON_TEMP_CONFIG,
            )
        return await self._conn.run(command, *args, **kwargs)


def _merge_clients_script_json_temp() -> str:
    script = _original_merge_clients_script()

    if LEGACY_TEMP_CONFIG not in script:
        raise RuntimeError(
            "Xray JSON temp compatibility patch: merge-script signature changed"
        )

    return script.replace(
        LEGACY_TEMP_CONFIG,
        JSON_TEMP_CONFIG,
    )


async def _ensure_modern_xray_json_temp(
    conn,
    base_port: int,
    node=None,
    *,
    bootstrap_done: bool = False,
):
    # A failed pre-fix repair can leave the historical candidate behind.
    # Remove only that obsolete temporary file; active config/state are never
    # touched here.
    await provision.cmd(
        conn,
        f"rm -f {LEGACY_TEMP_CONFIG}",
        check=False,
    )

    proxy = _JsonTempPathConnection(conn)

    return await _original_ensure_modern_xray(
        proxy,
        base_port,
        node,
        bootstrap_done=bootstrap_done,
    )


def apply_xray_modern_temp_config_runtime() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    # `_ensure_modern_xray` resolves `_merge_clients_script` from its module
    # globals at call time, so patch both bindings before any Repair can run.
    xray_modern_runtime._merge_clients_script = (
        _merge_clients_script_json_temp
    )
    xray_modern_runtime._ensure_modern_xray = (
        _ensure_modern_xray_json_temp
    )

    # Repair V3 imported the ensure function by name during module import.
    # Update that local binding too so Repair, account delivery and generic
    # Modern installation all converge on the same JSON-suffixed candidate.
    from . import xray_modern_repair_runtime

    xray_modern_repair_runtime._ensure_modern_xray = (
        _ensure_modern_xray_json_temp
    )

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_MODERN_TEMP_CONFIG_RUNTIME_V1_ACTIVE "
        "json_temp_suffix=1 legacy_stale_cleanup=1",
        flush=True,
    )
