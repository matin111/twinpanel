from __future__ import annotations

import asyncio
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


SINGBOX_PROTOCOLS = set(_SINGBOX_PROTOCOLS) | set(STANDALONE_PROTOCOLS)

# Type=simple becomes active before the process necessarily binds listeners.
# Production rc.157 proved the immediate post-restart health sample can race
# the AnyTLS listener even though the install completes and the listener comes
# online moments later. Retry only install-time readiness; manual health stays
# fail-fast.
SINGBOX_READINESS_ATTEMPTS = 20
SINGBOX_READINESS_DELAY_SECONDS = 0.25

# Standalone services have the same systemd/listener ordering risk. Production
# rc.162 proved Sudoku could report service_or_listener_unhealthy immediately
# after restart while its v0.5.1 process was still initializing tables and then
# bound the configured listener moments later. Keep manual health fail-fast and
# retry only the install-time readiness sample.
STANDALONE_READINESS_ATTEMPTS = 20
STANDALONE_READINESS_DELAY_SECONDS = 0.25


async def _wait_for_singbox_health(
    conn,
    protocol: str,
    port: int | None,
    *,
    attempts: int = SINGBOX_READINESS_ATTEMPTS,
    delay_seconds: float = SINGBOX_READINESS_DELAY_SECONDS,
) -> dict[str, Any]:
    tries = max(1, int(attempts))
    last: dict[str, Any] | None = None

    for index in range(tries):
        last = await _singbox_health(conn, protocol, port)
        if bool(last.get("ok")):
            return last
        if index + 1 < tries and delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return last or {
        "ok": False,
        "protocol": protocol,
        "port": port,
        "error": "service_or_listener_unhealthy",
    }


async def _wait_for_standalone_health(
    conn,
    protocol: str,
    port: int | None,
    *,
    attempts: int = STANDALONE_READINESS_ATTEMPTS,
    delay_seconds: float = STANDALONE_READINESS_DELAY_SECONDS,
) -> dict[str, Any]:
    tries = max(1, int(attempts))
    last: dict[str, Any] | None = None

    for index in range(tries):
        last = await standalone_health(conn, protocol, port)
        if bool(last.get("ok")):
            return last
        if index + 1 < tries and delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return last or {
        "ok": False,
        "protocol": protocol,
        "port": port,
        "error": "service_or_listener_unhealthy",
    }


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
        await ensure_singbox_service_unit(conn)
        singbox = await _apply_singbox_profiles(conn, node, singbox_profiles)

        singbox_results = singbox.setdefault("protocols", {})
        for profile in singbox_profiles:
            protocol = str(profile.get("protocol") or "").strip().lower()
            current = singbox_results.get(protocol)
            if isinstance(current, dict) and current.get("ok"):
                continue
            raw_port = profile.get("port")
            port = int(raw_port) if raw_port is not None else None
            singbox_results[protocol] = await _wait_for_singbox_health(
                conn,
                protocol,
                port,
            )

        result["core"]["sing-box"] = singbox.get("core", {})
        result["protocols"].update(singbox_results)

    for profile in standalone_profiles:
        protocol = str(profile.get("protocol") or "").strip().lower()
        standalone = await apply_standalone_profile(conn, node, profile)
        core = standalone.pop("core", {})
        if not bool(standalone.get("ok")):
            raw_port = profile.get("port")
            port = int(raw_port) if raw_port is not None else None
            readiness = await _wait_for_standalone_health(
                conn,
                protocol,
                port,
            )
            for key, value in standalone.items():
                readiness.setdefault(key, value)
            standalone = readiness
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
