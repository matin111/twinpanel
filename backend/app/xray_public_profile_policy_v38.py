from __future__ import annotations

from . import xray_public_delivery_runtime
from .xray_tcp_tls_v39 import (
    PROFILE_TCP_TLS,
    apply_xray_tcp_tls_v39,
)
from .xray_tcp_tls_admin_v39 import (
    apply_xray_tcp_tls_admin_v39,
)
from .xray_reconcile_infra_v41 import (
    apply_xray_reconcile_infra_v41,
)
from .xray_tcp_tls_compat_v44 import (
    apply_xray_tcp_tls_compat_v44,
)


# TWINPANEL_XRAY_PUBLIC_PROFILE_POLICY_V44
#
# Production findings:
# - WebSocket TLS is working through the Iran ingress.
# - HTTPUpgrade TLS is working through the Iran ingress.
# - gRPC Reality is operational and has a healthy service route.
# - TCP TLS service routing exists, but Xray 26.3.x rejected the V39 candidate
#   config because the temporary filename did not end in `.json`.
# - XHTTP Reality is intentionally hidden because it does not work on the
#   current customer path.
# - Plain/legacy VLESS TCP stays hidden from customers.
#
# Customer-visible order after V44:
#   1. WebSocket TLS
#   2. HTTPUpgrade TLS
#   3. TCP TLS
#   4. gRPC Reality
#
# The existing self_hosted_runtime hook name is intentionally preserved.

_runtime_applied = False

_PUBLIC_PROFILE_ORDER_V44 = (
    "websocket_tls",
    "httpupgrade_tls",
    PROFILE_TCP_TLS,
    "grpc_reality",
)


def apply_xray_public_profile_policy_v38() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    apply_xray_tcp_tls_v39()
    apply_xray_tcp_tls_compat_v44()
    apply_xray_tcp_tls_admin_v39()
    apply_xray_reconcile_infra_v41()

    xray_public_delivery_runtime._PUBLIC_PROFILE_ORDER = (
        _PUBLIC_PROFILE_ORDER_V44
    )
    xray_public_delivery_runtime._PUBLIC_PROFILE_IDS = set(
        _PUBLIC_PROFILE_ORDER_V44
    )

    _runtime_applied = True

    print(
        "TWINPANEL_XRAY_PUBLIC_PROFILE_POLICY_V44_ACTIVE "
        "websocket_tls=public "
        "httpupgrade_tls=public "
        "tcp_tls=public "
        "grpc_reality=public "
        "tcp_tls_candidate_json_fix=1 "
        "xhttp_reality=hidden_from_customer "
        "tcp_simple=hidden_from_customer",
        flush=True,
    )
