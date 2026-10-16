from __future__ import annotations

from . import xray_public_delivery_runtime


# TWINPANEL_XRAY_PUBLIC_PROFILE_POLICY_V38
#
# Production observation:
# - WebSocket TLS through Iran ingress is working reliably.
# - XHTTP Reality is not working for the current customer path.
#
# V38 changes only customer delivery policy. It does not remove listeners,
# credentials, ports, keys, or runtime fallback capability from the Exit node.
# XHTTP Reality remains available internally for rollback/diagnostics, but it is
# no longer offered on the public connection page.
#
# Customer-safe order:
#   1. WebSocket TLS (primary, already proven working)
#   2. HTTPUpgrade TLS (secure TLS fallback using the same domain/certificate)
#   3. Legacy VLESS TCP (compatibility fallback only)

_runtime_applied = False

_PUBLIC_PROFILE_ORDER_V38 = (
    "websocket_tls",
    "httpupgrade_tls",
    "tcp_simple",
)


def apply_xray_public_profile_policy_v38() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    xray_public_delivery_runtime._PUBLIC_PROFILE_ORDER = (
        _PUBLIC_PROFILE_ORDER_V38
    )
    xray_public_delivery_runtime._PUBLIC_PROFILE_IDS = set(
        _PUBLIC_PROFILE_ORDER_V38
    )

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_PUBLIC_PROFILE_POLICY_V38_ACTIVE "
        "websocket_tls=primary "
        "httpupgrade_tls=secure_fallback "
        "xhttp_reality=hidden_from_customer "
        "tcp_simple=compatibility_fallback",
        flush=True,
    )
