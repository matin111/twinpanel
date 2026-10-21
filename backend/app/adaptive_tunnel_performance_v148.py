from __future__ import annotations

from . import vpn_access_performance_v51 as access_performance
from .transport_candidates import tp27_fast


# ============================================================
# TWINPANEL ADAPTIVE TUNNEL PERFORMANCE V148
#
# Production facts behind this contract:
#   * TP27 Fast native GRE is already healthy at MTU 1400 and has sustained
#     high bidirectional carrier throughput on the real Iran <-> Exit pair.
#   * Routed VPN access was still globally forced to MTU 1200 / MSS 1160.
#   * Xray does not use that routed client-pool dataplane and has been
#     materially better than the routed VPN protocols in the same deployment.
#   * The standalone TP27 OpenVPN reference uses a 1300-byte default MTU.
#
# V148 therefore does NOT change the proven 1400-byte carrier and does NOT
# touch GRE/FoU selection. It only removes unnecessary nested-MTU overhead by
# deriving a conservative routed-access MTU from the proven carrier:
#
#     1400 carrier - 100 bytes overlay headroom = 1300 access MTU
#     1300 IPv4 MTU - 40 bytes TCP/IP headers = 1260 MSS
#
# The 100-byte margin leaves room for OpenVPN/WireGuard/IPsec encapsulation and
# keeps modern UDP-heavy services on the protocol-agnostic L3 carrier instead
# of forcing a TCP fallback. Exit Access Stability V144 remains authoritative
# for read-only steady state and drift-only repair.
# ============================================================

MARKER = "TWINPANEL_ADAPTIVE_TUNNEL_PERFORMANCE_V148"

TP27_CARRIER_MTU = 1400
ACCESS_OVERLAY_HEADROOM = 100
ACCESS_MTU = TP27_CARRIER_MTU - ACCESS_OVERLAY_HEADROOM
IPV4_TCP_HEADER_BYTES = 40
ACCESS_TCP_MSS = ACCESS_MTU - IPV4_TCP_HEADER_BYTES

_applied = False


def _validate_contract() -> None:
    carrier_mtu = int(getattr(tp27_fast, "MTU", 0) or 0)

    if carrier_mtu != TP27_CARRIER_MTU:
        raise RuntimeError(
            "adaptive_tunnel_v148_carrier_contract_changed:"
            f"expected={TP27_CARRIER_MTU}:actual={carrier_mtu}"
        )

    if ACCESS_MTU != 1300:
        raise RuntimeError(
            "adaptive_tunnel_v148_access_mtu_contract_invalid"
        )

    if ACCESS_TCP_MSS != 1260:
        raise RuntimeError(
            "adaptive_tunnel_v148_access_mss_contract_invalid"
        )

    if ACCESS_OVERLAY_HEADROOM < 80:
        raise RuntimeError(
            "adaptive_tunnel_v148_overlay_headroom_too_small"
        )


def apply_adaptive_tunnel_performance_v148() -> None:
    """Apply the V148 nested-MTU contract before V144 wraps V51.

    ``vpn_access_performance_v51._performance_script`` reads its module-level
    MTU/MSS constants when it renders each reconciliation script. Updating the
    constants here preserves the mature V51 repair implementation while V144
    continues to short-circuit unchanged Desired State with zero live-chain
    mutation.
    """

    global _applied

    if _applied:
        return

    _validate_contract()

    access_performance.ACCESS_MTU = ACCESS_MTU
    access_performance.ACCESS_TCP_MSS = ACCESS_TCP_MSS

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        f"carrier_mtu={TP27_CARRIER_MTU} "
        f"access_mtu={ACCESS_MTU} "
        f"tcp_mss={ACCESS_TCP_MSS} "
        f"headroom={ACCESS_OVERLAY_HEADROOM} "
        "carrier=unchanged "
        "steady_state=v144-read-only",
        flush=True,
    )
