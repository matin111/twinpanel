from __future__ import annotations

from . import xray_public_delivery_runtime
from .xray_tcp_tls_v39 import (
    PROFILE_TCP_TLS,
    apply_xray_tcp_tls_v39,
)
from .xray_tcp_tls_admin_v39 import (
    apply_xray_tcp_tls_admin_v39,
)


# TWINPANEL_XRAY_PUBLIC_PROFILE_POLICY_V39
#
# Production observation:
# - WebSocket TLS through Iran ingress is working reliably.
# - XHTTP Reality is not working for the current customer path.
# - Plain VLESS TCP is intentionally not exposed to customers.
#
# V39 keeps only TLS-backed customer profiles. Internal XHTTP/Reality and legacy
# plain TCP remain available for rollback/diagnostics but are never rendered on
# the customer connection page.
#
# Customer-safe order:
#   1. WebSocket TLS (primary, proven working)
#   2. HTTPUpgrade TLS (domain-backed fallback)
#   3. TCP TLS (simple secure fallback, no plain TCP)

_runtime_applied = False

_PUBLIC_PROFILE_ORDER_V39 = (
    "websocket_tls",
    "httpupgrade_tls",
    PROFILE_TCP_TLS,
)


def apply_xray_public_profile_policy_v38() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    # Keep the existing self_hosted_runtime hook name stable while upgrading the
    # actual customer profile policy to V39.
    apply_xray_tcp_tls_v39()
    apply_xray_tcp_tls_admin_v39()

    xray_public_delivery_runtime._PUBLIC_PROFILE_ORDER = (
        _PUBLIC_PROFILE_ORDER_V39
    )
    xray_public_delivery_runtime._PUBLIC_PROFILE_IDS = set(
        _PUBLIC_PROFILE_ORDER_V39
    )

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_PUBLIC_PROFILE_POLICY_V39_ACTIVE "
        "websocket_tls=primary "
        "httpupgrade_tls=secure_fallback "
        "tcp_tls=secure_fallback "
        "xhttp_reality=hidden_from_customer "
        "tcp_simple=hidden_from_customer",
        flush=True,
    )
