from __future__ import annotations

from . import smart_transport_auto_v21 as smart
from . import tp27_reference_runtime_v91 as reference_v91


# ============================================================
# TWINPANEL ADAPTIVE MULTI-LANE V150
#
# Keep three independent carrier families warm:
#   1) tp27_fast       -> native GRE first, FoU only install fallback
#   2) tp27_masque     -> RFC 9484 CONNECT-IP over HTTP/3 / QUIC
#   3) tp27_tcp_direct -> independent direct TCP L3 carrier
#
# MASQUE is UDP-dependent and is never hard-preferred. SmartAuto V21 remains
# authoritative for health, packet loss, jitter, throughput and promotion.
# Direct TCP remains available when Iran UDP quality is degraded.
# ============================================================

MARKER = "TWINPANEL_ADAPTIVE_MULTILANE_V150"

_applied = False
_original_v91_policy = reference_v91.activate_manager_candidate_policy_v91


def _apply_lane_policy() -> None:
    _original_v91_policy()
    smart.AUTO_INSTALL_NAMES = (
        "tp27_fast",
        "tp27_masque",
        "tp27_tcp_direct",
    )


def apply_adaptive_multilane_v150() -> None:
    global _applied

    if _applied:
        return

    expected = {
        "tp27_fast",
        "tp27_masque",
        "tp27_tcp_direct",
    }
    available = set(smart.CANDIDATE_NAMES)
    missing = sorted(expected - available)

    if missing:
        raise RuntimeError(
            "adaptive_multilane_v150_candidates_missing:"
            + ",".join(missing)
        )

    _apply_lane_policy()

    # The V91 reconciler reapplies its candidate policy when its task starts.
    # Keep that later call V150-aware so it cannot narrow the active set.
    reference_v91.activate_manager_candidate_policy_v91 = _apply_lane_policy

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "lanes=tp27_fast,tp27_masque,tp27_tcp_direct "
        "masque=connect-ip-h3 "
        "udp_policy=quality-gated "
        "non_udp_fallback=tp27_tcp_direct "
        "failover=smartauto-v21",
        flush=True,
    )
