from __future__ import annotations

from . import vpn_access_dataplane_v46 as v46


# ============================================================
# TWINPANEL VPN ACCESS DATAPLANE V53
#
# V46 correctly owns Exit-side NAT/FORWARD for the RFC1918 client pools, but
# historically decided which pool rules to install from NodeProtocolConfig
# status telemetry. That is unsafe for the data plane: a stale/offline status
# can make V46 flush a perfectly valid pool from TP_ACCESS_EGRESS/TP_ACCESS_FWD
# while a real VPN session is active. The client then keeps its VPN default
# route, so the whole Internet appears to die even though the outer VPN control
# connection remains established.
#
# V53 changes only the egress eligibility policy. Every non-retired Exit keeps
# NAT/FORWARD/MSS rules for all four managed access pools at all times. Missing
# protocol daemons are harmless because unused pool rules never match traffic.
# OpenVPN PKI activation keeps its existing status gate inside V46; only client
# egress rule ownership becomes status-independent.
# ============================================================

_ALWAYS_ON_ACCESS_PROTOCOLS = frozenset(v46._PROTOCOL_SUBNETS.keys())


def _all_access_protocols(_db, _node_id: int) -> set[str]:
    return set(_ALWAYS_ON_ACCESS_PROTOCOLS)


def install_vpn_access_dataplane_v53() -> None:
    """Make V46 egress reconciliation independent of dashboard telemetry."""

    v46._enabled_access_protocols = _all_access_protocols
