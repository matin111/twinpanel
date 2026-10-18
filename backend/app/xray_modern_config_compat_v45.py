from __future__ import annotations

from types import ModuleType
from typing import Any

from . import xray_modern_runtime


# TWINPANEL_XRAY_MODERN_CONFIG_COMPAT_V45
#
# Xray 26.3.x determines the config format from the final filename suffix.
# Modern Runtime V2 historically used:
#   /usr/local/etc/xray/config.json.twinpanel-modern
# which is valid JSON content but no longer has a .json suffix. Xray therefore
# rejects the candidate before any listener can be reconciled with:
#   Failed to get format of ...config.json.twinpanel-modern
#
# Keep the proven V2 config builder, client-preservation logic, ports, UUIDs and
# rollback behavior intact. Only redirect the temporary candidate path to a
# filename ending in .json, including the embedded merge-clients script.

_OLD_CANDIDATE = "/usr/local/etc/xray/config.json.twinpanel-modern"
_NEW_CANDIDATE = "/usr/local/etc/xray/config.twinpanel-modern-v45.json"

_runtime_applied = False
_original_shlex: ModuleType | Any | None = None
_original_merge_clients_script = None


class _ShlexCompatProxy:
    def __init__(self, original: Any):
        self._original = original

    def quote(self, value: str) -> str:
        target = _NEW_CANDIDATE if value == _OLD_CANDIDATE else value
        return self._original.quote(target)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


def _merge_clients_script_v45() -> str:
    assert _original_merge_clients_script is not None

    script = _original_merge_clients_script()

    if _NEW_CANDIDATE in script:
        return script

    if _OLD_CANDIDATE not in script:
        raise RuntimeError(
            "V45 cannot locate the Modern Xray candidate path"
        )

    return script.replace(
        _OLD_CANDIDATE,
        _NEW_CANDIDATE,
    )


def apply_xray_modern_config_compat_v45() -> None:
    global _runtime_applied
    global _original_shlex
    global _original_merge_clients_script

    if _runtime_applied:
        return

    _original_shlex = xray_modern_runtime.shlex
    _original_merge_clients_script = (
        xray_modern_runtime._merge_clients_script
    )

    xray_modern_runtime.shlex = _ShlexCompatProxy(
        _original_shlex
    )
    xray_modern_runtime._merge_clients_script = (
        _merge_clients_script_v45
    )

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_MODERN_CONFIG_COMPAT_V45_ACTIVE "
        "candidate_json_suffix=1 xray_26_3_compatible=1 "
        "ports_unchanged=1 uuid_preserved=1 rollback_preserved=1",
        flush=True,
    )
