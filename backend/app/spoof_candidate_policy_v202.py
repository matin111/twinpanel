from __future__ import annotations

from . import smart_transport_auto_v21 as smart
from . import tp27_reference_runtime_v91 as reference_v91
from . import transport_candidates as candidates
from .tp6_candidate_registry_v208 import apply_tp6_candidate_registry_v208


# ============================================================
# TWINPANEL SPOOF CANDIDATE POLICY V202
#
# Production policy after the rc.201 investigation:
#   * keep the proven TP27 Fast path unchanged;
#   * keep Spoof WG as an explicit-config candidate;
#   * add TP6 Fast as an explicit-install IPv6 carrier candidate;
#   * never auto-install Spoof WG because its mutual-spoof source addresses
#     must be explicitly configured and verified by the administrator;
#   * retire MASQUE, Mieru TCP and Direct TCP from install/health/promotion;
#   * retain their runtime/uninstall handlers so V91 can remove old services
#     only after a tunnel is already proven online on TP27 Fast.
# ============================================================

MARKER = "TWINPANEL_SPOOF_CANDIDATE_POLICY_V202"
ACTIVE = frozenset({"tp27_fast", "tp6_fast", "spoof_wg"})
RETIRED = (
    "tp27_masque",
    "tp27_mieru_tcp",
    "tp27_tcp_direct",
)

_applied = False


def _apply_active_policy() -> None:
    # TP27 Fast remains the only automatic installer. Spoof WG and TP6 Fast
    # become eligible for health/benchmark/promotion only after explicit install.
    smart.AUTO_INSTALL_NAMES = ("tp27_fast",)
    smart.CANDIDATE_NAMES = ACTIVE
    smart.ALL_AUTO_NAMES = ACTIVE

    print(
        f"{MARKER}_SMARTAUTO "
        "active=tp27_fast,tp6_fast,spoof_wg "
        "auto_install=tp27_fast "
        "spoof_install=explicit-config-only "
        "tp6_install=explicit-only "
        "retired=tp27_masque,tp27_mieru_tcp,tp27_tcp_direct",
        flush=True,
    )


def apply_spoof_candidate_policy_v202() -> None:
    global _applied
    if _applied:
        return

    # TP6 is registered additively before the final active-set policy is
    # validated. The historical transport_candidates/__init__.py stays intact.
    apply_tp6_candidate_registry_v208()

    # V165 may have re-added Mieru into the process-local registry. Remove all
    # three failed experimental lanes from every production-facing registry,
    # while leaving SPECS/runtime/uninstall compatibility in place.
    for name in RETIRED:
        candidates.ACTIVE_SPECS.pop(name, None)
        candidates.INSTALLERS.pop(name, None)

    if "tp27_fast" not in candidates.ACTIVE_SPECS:
        raise RuntimeError("spoof_policy_tp27_fast_missing")
    if "spoof_wg" not in candidates.ACTIVE_SPECS:
        raise RuntimeError("spoof_policy_spoof_wg_missing")
    if "tp6_fast" not in candidates.ACTIVE_SPECS:
        raise RuntimeError("spoof_policy_tp6_fast_missing")

    _apply_active_policy()

    # V91 reapplies its policy when its reconciler task starts. Make that late
    # call V202-aware so older adaptive layers cannot expand Auto again.
    reference_v91.activate_manager_candidate_policy_v91 = _apply_active_policy

    # V91 cleanup already uses the official uninstall lifecycle and only acts
    # after a tunnel is active + online on TP27 Fast. Extend that proven cleanup
    # contract to the three newly retired lanes. Their source handlers remain
    # in-tree specifically so this cleanup stays reversible and scoped.
    retired = list(reference_v91.RETIRED_CANDIDATES)
    for name in RETIRED:
        if name not in retired:
            retired.append(name)
    reference_v91.RETIRED_CANDIDATES = tuple(retired)

    _applied = True
    print(
        f"{MARKER}_ACTIVE "
        "active_candidates=tp27_fast,tp6_fast,spoof_wg "
        "auto_install=tp27_fast "
        "retired_cleanup=official-v91-after-fast-online",
        flush=True,
    )
