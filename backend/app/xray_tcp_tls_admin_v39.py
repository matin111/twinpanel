from __future__ import annotations

from typing import Any

from . import (
    tunnel_service_connections_admin_runtime,
    xray_modern_admin,
    xray_modern_repair_runtime,
    xray_modern_runtime,
)
from .routers import provision
from .xray_tcp_tls_v39 import (
    PROFILE_TCP_TLS,
    _tcp_tls_public_port,
    _tcp_tls_target_port,
)


# TWINPANEL_XRAY_TCP_TLS_ADMIN_V39
#
# Keep the existing admin/repair/service-inventory modules aware of the TCP TLS
# listener. Several historical modules imported helpers by name, so updating
# only xray_modern_runtime would leave their local bindings stale.

_runtime_applied = False
_original_health_snapshot = None
_original_admin_status_remote = None
_original_admin_profile_rows = None
_original_connection_health = None


async def _health_snapshot_v39(conn, base_port: int) -> dict[str, Any]:
    assert _original_health_snapshot is not None

    result = dict(await _original_health_snapshot(conn, int(base_port)))
    listeners = dict(result.get("listeners") or {})
    ports = dict(result.get("ports") or {})

    port = _tcp_tls_target_port(int(base_port))
    listener_ok = bool(await provision.listener(conn, port, "tcp"))

    ports[PROFILE_TCP_TLS] = port
    listeners[PROFILE_TCP_TLS] = listener_ok

    result["ports"] = ports
    result["listeners"] = listeners

    missing = [
        str(item)
        for item in (result.get("missing") or [])
        if str(item) != "tcp_tls_listener"
    ]

    if bool(result.get("tls_enabled")) and not listener_ok:
        missing.append("tcp_tls_listener")

    result["missing"] = missing
    result["ok"] = bool(result.get("ok")) and not missing

    if missing and not result.get("error"):
        result["error"] = "missing health checks: " + ", ".join(missing)

    return result


async def _admin_status_remote_v39(conn, base_port: int) -> dict[str, Any]:
    assert _original_admin_status_remote is not None

    result = dict(await _original_admin_status_remote(conn, int(base_port)))
    profiles = dict(result.get("profiles") or {})
    profiles[PROFILE_TCP_TLS] = bool(
        await provision.listener(
            conn,
            _tcp_tls_target_port(int(base_port)),
            "tcp",
        )
    )
    result["profiles"] = profiles
    return result


def _admin_profile_rows_v39(node, base_port: int) -> list[dict[str, Any]]:
    assert _original_admin_profile_rows is not None

    rows = list(_original_admin_profile_rows(node, int(base_port)))
    if any(str(row.get("id") or "") == PROFILE_TCP_TLS for row in rows):
        return rows

    rows.append(
        {
            "id": PROFILE_TCP_TLS,
            "title": "VLESS TCP TLS",
            "security": "tls",
            "transport": "tcp",
            "recommended": False,
            "requires_tls_domain": True,
            "target_port": _tcp_tls_target_port(int(base_port)),
            "tunnel_public_port": _tcp_tls_public_port(int(node.id)),
        }
    )
    return rows


def _connection_health_v39(
    *,
    protocol: str,
    profile: str,
    config_online: bool,
    xray_health: dict[str, Any] | None,
):
    assert _original_connection_health is not None

    if str(protocol).strip().lower() != "v2ray" or str(profile).strip().lower() != PROFILE_TCP_TLS:
        return _original_connection_health(
            protocol=protocol,
            profile=profile,
            config_online=config_online,
            xray_health=xray_health,
        )

    if not xray_health:
        return None, True, "xray_health_not_probed"

    if not bool(xray_health.get("tls_enabled")):
        return False, False, "tls_domain_unavailable"

    listeners = xray_health.get("listeners")
    if not isinstance(listeners, dict) or PROFILE_TCP_TLS not in listeners:
        return None, True, "listener_health_unknown"

    listener_ok = bool(listeners.get(PROFILE_TCP_TLS))
    return (
        listener_ok,
        True,
        None if listener_ok else "listener_not_running",
    )


def apply_xray_tcp_tls_admin_v39() -> None:
    global _runtime_applied
    global _original_health_snapshot
    global _original_admin_status_remote
    global _original_admin_profile_rows
    global _original_connection_health

    if _runtime_applied:
        return

    # Admin and repair modules imported _ensure_modern_xray by name. Point those
    # bindings at the final V39 wrapper so prepare/repair never rebuilds Xray
    # without the TCP TLS listener.
    xray_modern_admin._ensure_modern_xray = xray_modern_runtime._ensure_modern_xray
    xray_modern_repair_runtime._ensure_modern_xray = xray_modern_runtime._ensure_modern_xray

    _original_health_snapshot = xray_modern_repair_runtime._modern_health_snapshot
    xray_modern_repair_runtime._modern_health_snapshot = _health_snapshot_v39
    tunnel_service_connections_admin_runtime._modern_health_snapshot = _health_snapshot_v39

    _original_admin_status_remote = xray_modern_admin._status_remote
    xray_modern_admin._status_remote = _admin_status_remote_v39

    _original_admin_profile_rows = xray_modern_admin._profile_rows
    xray_modern_admin._profile_rows = _admin_profile_rows_v39

    _original_connection_health = tunnel_service_connections_admin_runtime._connection_health
    tunnel_service_connections_admin_runtime._connection_health = _connection_health_v39
    tunnel_service_connections_admin_runtime._XRAY_PROFILE_TITLES[PROFILE_TCP_TLS] = "TCP TLS"

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_TCP_TLS_ADMIN_V39_ACTIVE "
        "admin_prepare=1 repair=1 health=1 service_inventory=1",
        flush=True,
    )
