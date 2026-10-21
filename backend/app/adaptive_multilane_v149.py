from __future__ import annotations

from . import smart_transport_auto_v21 as smart


# ============================================================
# TWINPANEL ADAPTIVE MULTI-LANE V149
#
# Keep multiple independent carrier families warm so a degraded path can be
# replaced without rebuilding the whole tunnel stack:
#   1) tp27_fast       -> native GRE first, FoU only as its install fallback
#   2) tp27_tcp_direct -> independent direct TCP L3 carrier
#
# SmartAuto remains authoritative for health, packet-loss, latency, throughput,
# quarantine, dwell and promotion. V149 only expands the installable candidate
# set; it does not force TCP when native GRE remains faster and healthy.
# ============================================================

MARKER = "TWINPANEL_ADAPTIVE_MULTILANE_V149"

_applied = False


def apply_adaptive_multilane_v149() -> None:
    global _applied

    if _applied:
        return

    expected = {"tp27_fast", "tp27_tcp_direct"}
    available = set(smart.CANDIDATE_NAMES)
    missing = sorted(expected - available)

    if missing:
        raise RuntimeError(
            "adaptive_multilane_v149_candidates_missing:"
            + ",".join(missing)
        )

    # Install GRE-family first because it is the proven low-overhead path.
    # Keep direct TCP warm as an independently benchmarked fallback for periods
    # where Iran-side UDP/FoU quality is degraded or protocol 47 is unavailable.
    smart.AUTO_INSTALL_NAMES = (
        "tp27_fast",
        "tp27_tcp_direct",
    )

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "lanes=tp27_fast,tp27_tcp_direct "
        "primary=health-and-speed "
        "udp_dependency=not-required "
        "failover=smartauto-v21",
        flush=True,
    )
