from __future__ import annotations

from . import vpn_access_dataplane_v46 as v46


# ============================================================
# TWINPANEL VPN ACCESS DATAPLANE V53
#
# V46 owns Exit-side NAT/FORWARD for the RFC1918 client pools, but historically
# derived which pool rules to publish from NodeProtocolConfig.status telemetry.
# That is unsafe for the data plane: one stale/offline heartbeat can make V46
# flush a live pool from TP_ACCESS_EGRESS/TP_ACCESS_FWD while a VPN session is
# still connected. The client then keeps its VPN default route but Internet is
# blackholed. Xray/V2Ray does not use these pool chains, which explains the
# production symptom where Xray has data while Cisco/OpenVPN/WireGuard/L2TP do
# not.
#
# V53 changes only egress eligibility. Every non-retired Exit continuously owns
# NAT/FORWARD/MSS rules for all four managed access pools. Missing daemons are
# harmless because unused RFC1918 pool rules never match traffic. OpenVPN PKI
# activation keeps its existing V46 runtime/status gate; credentials, quota,
# service listeners, Unified L3 election and tunnel routing are unchanged.
# ============================================================

_ALWAYS_ON_ACCESS_PROTOCOLS = frozenset(v46._PROTOCOL_SUBNETS.keys())


def _all_access_protocols(_db, _node_id: int) -> set[str]:
    return set(_ALWAYS_ON_ACCESS_PROTOCOLS)


def install_vpn_access_dataplane_v53() -> None:
    """Make V46 egress reconciliation independent of dashboard telemetry."""

    v46._enabled_access_protocols = _all_access_protocols
