from __future__ import annotations

from . import smart_transport_auto_v21 as smart
from . import tp27_reference_runtime_v91 as reference_v91


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
_original_v91_policy = reference_v91.activate_manager_candidate_policy_v91


def _apply_lane_policy() -> None:
    # Preserve every V91 retirement/migration decision first, then expand only
    # the active install set with the new independent direct-TCP lane.
    _original_v91_policy()
    smart.AUTO_INSTALL_NAMES = (
        "tp27_fast",
        "tp27_tcp_direct",
    )


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

    _apply_lane_policy()

    # tp27_reference_runtime_v91.reconciler_loop invokes its policy function at
    # task startup. Replace that module-level binding so V91 cannot later narrow
    # AUTO_INSTALL_NAMES back to a single lane after V149 has activated.
    reference_v91.activate_manager_candidate_policy_v91 = _apply_lane_policy

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "lanes=tp27_fast,tp27_tcp_direct "
        "primary=health-and-speed "
        "udp_dependency=not-required "
        "failover=smartauto-v21",
        flush=True,
    )
