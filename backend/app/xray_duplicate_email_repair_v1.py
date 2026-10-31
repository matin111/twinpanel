from __future__ import annotations

from . import xray_modern_runtime


_runtime_applied = False
_original_merge_clients_script = None


def install() -> None:
    """Allow modern Xray bootstrap to heal legacy duplicate-email drift.

    Older account mutation updated only the first VLESS inbound. A retry could
    therefore leave the same subscription email mapped to different UUIDs across
    the remaining modern inbounds. The modern bootstrap must normalize that
    historical drift before its authoritative client-sync step can replace the
    identity on every inbound.
    """

    global _runtime_applied, _original_merge_clients_script

    if _runtime_applied:
        return

    original = xray_modern_runtime._merge_clients_script
    _original_merge_clients_script = original

    def _merge_clients_script_repair() -> str:
        script = original()
        needle = 'raise RuntimeError("Xray duplicate email conflict")'
        if needle not in script:
            raise RuntimeError("Xray duplicate-email merge contract changed")

        # Preserve the first valid identity for a duplicated email and ignore
        # later conflicting copies. _client_sync_script() immediately follows
        # bootstrap and atomically rewrites that email to the requested UUID on
        # every VLESS inbound, so no stale identity is delivered to the user.
        return script.replace(needle, "continue", 1)

    xray_modern_runtime._merge_clients_script = _merge_clients_script_repair
    _runtime_applied = True
    print(
        "TWINPANEL_XRAY_DUPLICATE_EMAIL_REPAIR_V1_ACTIVE",
        flush=True,
    )
