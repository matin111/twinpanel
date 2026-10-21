from __future__ import annotations

from typing import Any

from .modern_protocol_runtime_v2 import (
    SINGBOX_PROTOCOLS as _SINGBOX_PROTOCOLS,
    ModernRuntimeV2Error,
    apply_profiles as _apply_singbox_profiles,
    profile_health as _singbox_health,
    redacted_preview as _singbox_preview,
    remove_profile as _remove_singbox_profile,
)
from .singbox_service_runtime import ensure_singbox_service_unit
from .standalone_protocol_runtime import (
    STANDALONE_PROTOCOLS,
    StandaloneProtocolError,
    apply_standalone_profile,
    standalone_health,
    standalone_preview,
    remove_standalone,
)


# Kept under the historical exported name so the existing admin router can use
# the same install/health/remove guards without duplicating dispatch logic.
SINGBOX_PROTOCOLS = set(_SINGBOX_PROTOCOLS) | set(STANDALONE_PROTOCOLS)


async def apply_profiles(conn, node, profiles: list[dict[str, Any]]) -> dict[str, Any]:
    singbox_profiles = [
        item for item in profiles
        if str(item.get("protocol") or "").strip().lower() in _SINGBOX_PROTOCOLS
    ]
    standalone_profiles = [
        item for item in profiles
        if str(item.get("protocol") or "").strip().lower() in STANDALONE_PROTOCOLS
    ]
    if len(singbox_profiles) + len(standalone_profiles) != len(profiles):
        unknown = [
            str(item.get("protocol") or "")
            for item in profiles
            if str(item.get("protocol") or "").strip().lower() not in SINGBOX_PROTOCOLS
        ]
        raise ModernRuntimeV2Error(f"protocol runtime is not available: {', '.join(unknown)}")

    result: dict[str, Any] = {"core": {}, "protocols": {}}
    if singbox_profiles:
        # V2/V3 applies profiles by restarting the managed service after a
        # successful config check. Clean nodes (including Local Core) may have
        # the sing-box package but no TwinPanel service unit yet, so converge
        # the unit first without starting it before a valid config exists.
        await ensure_singbox_service_unit(conn)
        singbox = await _apply_singbox_profiles(conn, node, singbox_profiles)
        result["core"]["sing-box"] = singbox.get("core", {})
        result["protocols"].update(singbox.get("protocols", {}))

    for profile in standalone_profiles:
        protocol = str(profile.get("protocol") or "").strip().lower()
        standalone = await apply_standalone_profile(conn, node, profile)
        core = standalone.pop("core", {})
        result["core"][protocol] = core
        result["protocols"][protocol] = standalone

    return result


async def profile_health(conn, protocol: str, port: int | None = None) -> dict[str, Any]:
    key = str(protocol or "").strip().lower()
    if key in _SINGBOX_PROTOCOLS:
        return await _singbox_health(conn, key, port)
    if key in STANDALONE_PROTOCOLS:
        return await standalone_health(conn, key, port)
    raise ModernRuntimeV2Error(f"protocol runtime is not available: {key}")


async def remove_profile(conn, protocol: str) -> dict[str, Any]:
    key = str(protocol or "").strip().lower()
    if key in _SINGBOX_PROTOCOLS:
        return await _remove_singbox_profile(conn, key)
    if key in STANDALONE_PROTOCOLS:
        return await remove_standalone(conn, key)
    raise ModernRuntimeV2Error(f"protocol runtime is not available: {key}")


def redacted_preview(protocol: str, port: int, settings: dict[str, Any]) -> dict[str, Any]:
    key = str(protocol or "").strip().lower()
    if key in _SINGBOX_PROTOCOLS:
        return _singbox_preview(key, port, settings)
    if key in STANDALONE_PROTOCOLS:
        return standalone_preview(key, port, settings)
    raise ModernRuntimeV2Error(f"protocol runtime is not available: {key}")


__all__ = [
    "SINGBOX_PROTOCOLS",
    "ModernRuntimeV2Error",
    "StandaloneProtocolError",
    "apply_profiles",
    "profile_health",
    "redacted_preview",
    "remove_profile",
]
