from __future__ import annotations

from . import unified_l3_agent_rollout_v49 as rollout
from . import unified_l3_core_v49 as core
from .active_l3_route_binding_v94 import apply_active_l3_route_binding_v94
from .service_routing_stability_v139 import (
    apply_service_routing_stability_v139,
)
from .transport_candidates import SPECS
from .tp6_candidate_registry_v208 import apply_tp6_candidate_registry_v208

AGENT_MARKER = "TWINPANEL_ACTIVE_TRANSPORT_AUTHORITY_V258"
_runtime_applied = False


_ACTIVE_SELECTION_ANCHOR = '''                if (
                    selected not in managed_candidates
                    or selected not in candidates
                ):
'''

_ACTIVE_SELECTION_REPLACEMENT = '''                # active_transport is the controller authority. transport_candidates
                # is capability/fallback ordering and may lag during a manual or
                # automatic carrier cutover. Never demote a known active carrier
                # merely because the legacy candidate list has not converged yet.
                if selected not in managed_candidates:
'''


def _candidate_literal() -> str:
    names = sorted(str(name).strip().lower() for name in SPECS)
    return "{" + ", ".join(repr(name) for name in names) + "}"


def apply_unified_l3_candidate_registry_v79() -> None:
    global _runtime_applied
    if _runtime_applied:
        return

    # Register TP6 additively before V79 snapshots the candidate literal.
    # This preserves the historical transport registry source contract while
    # allowing the existing Unified L3 Agent to understand TP6 as a managed lane.
    apply_tp6_candidate_registry_v208()
    apply_active_l3_route_binding_v94()

    source = core._AGENT_RECONCILE_V49
    candidates = _candidate_literal()

    if AGENT_MARKER not in source:
        managed_anchor = (
            '                "backhaul",\n'
            '            }\n\n'
            '            active_name = str('
        )
        managed_replacement = (
            '                "backhaul",\n'
            '            }\n\n'
            f'            managed_candidates.update({candidates})\n'
            f'            # {AGENT_MARKER}\n\n'
            '            active_name = str('
        )
        if managed_anchor not in source:
            raise RuntimeError("Unified L3 V49 managed-candidate contract changed; V79 registry patch refused")
        source = source.replace(managed_anchor, managed_replacement, 1)

        if _ACTIVE_SELECTION_ANCHOR not in source:
            raise RuntimeError("Unified L3 V49 active-transport authority contract changed; V79 patch refused")
        source = source.replace(
            _ACTIVE_SELECTION_ANCHOR,
            _ACTIVE_SELECTION_REPLACEMENT,
            1,
        )

        probe_anchor = '                if selected == "mtunnel":\n'
        probe_replacement = (
            '                if (\n'
            '                    selected == "mtunnel"\n'
            f'                    or selected in {candidates}\n'
            '                ):\n'
        )
        if probe_anchor not in source:
            raise RuntimeError("Unified L3 V49 carrier-probe contract changed; V79 registry patch refused")
        source = source.replace(probe_anchor, probe_replacement, 1)
        core._AGENT_RECONCILE_V49 = source

    missing = [name for name in sorted(SPECS) if repr(name) not in core._AGENT_RECONCILE_V49]
    if missing or AGENT_MARKER not in core._AGENT_RECONCILE_V49:
        raise RuntimeError("Unified L3 V79 candidate registry validation failed: " + ",".join(missing))

    if _ACTIVE_SELECTION_ANCHOR in core._AGENT_RECONCILE_V49:
        raise RuntimeError("Unified L3 V79 active-transport authority validation failed")

    # V139 patches the base Agent renderer after the candidate registry is
    # finalized but before Unified L3 V49 captures make_agent. Keep its routing
    # hardening, then restore this newer marker so startup rollout upgrades
    # existing Iran/Exit Agents to the active-transport authority fix.
    apply_service_routing_stability_v139()
    rollout._AGENT_MARKER = AGENT_MARKER

    _runtime_applied = True
    print(
        "TWINPANEL_UNIFIED_L3_CANDIDATE_REGISTRY_V79_ACTIVE "
        "source=transport_candidates.SPECS "
        f"candidates={','.join(sorted(SPECS))} route_binding=v94 "
        "active_transport_authority=v258 agent_rollout_marker=v258",
        flush=True,
    )
