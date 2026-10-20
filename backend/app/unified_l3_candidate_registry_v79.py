from __future__ import annotations

from . import unified_l3_agent_rollout_v49 as rollout
from . import unified_l3_core_v49 as core
from .transport_candidates import SPECS


# ============================================================
# TWINPANEL UNIFIED L3 CANDIDATE REGISTRY V79
#
# Smart Auto already uses transport_candidates.SPECS as the authoritative
# registry for modern isolated L3 candidates. Unified L3 V49 historically kept
# a second hard-coded managed-carrier set inside the rendered Node Agent, so a
# candidate could be selected by Smart Auto but still be treated as an unknown
# carrier by the Agent.
#
# V79 removes that split-brain behavior without changing protocol routing or
# transport selection policy: candidate names are injected from SPECS into the
# V49 Agent source before it is rendered, and those candidate interfaces are
# probed with the generic L3 carrier probe rather than the SSH-TUN-specific
# compatibility path.
# ============================================================

AGENT_MARKER = "TWINPANEL_UNIFIED_L3_CANDIDATE_REGISTRY_V79"
_runtime_applied = False


def _candidate_literal() -> str:
    names = sorted(str(name).strip().lower() for name in SPECS)
    return "{" + ", ".join(repr(name) for name in names) + "}"


def apply_unified_l3_candidate_registry_v79() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

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
            raise RuntimeError(
                "Unified L3 V49 managed-candidate contract changed; "
                "V79 registry patch refused"
            )

        source = source.replace(
            managed_anchor,
            managed_replacement,
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
            raise RuntimeError(
                "Unified L3 V49 carrier-probe contract changed; "
                "V79 registry patch refused"
            )

        source = source.replace(
            probe_anchor,
            probe_replacement,
            1,
        )

        core._AGENT_RECONCILE_V49 = source

    # Existing V49 Agents must not be considered current after this source
    # change. Rollout V49 now reads its marker dynamically, so pointing it at
    # V79 causes one bounded atomic re-render/restart and remains idempotent.
    rollout._AGENT_MARKER = AGENT_MARKER

    missing = [
        name
        for name in sorted(SPECS)
        if repr(name) not in core._AGENT_RECONCILE_V49
    ]
    if missing or AGENT_MARKER not in core._AGENT_RECONCILE_V49:
        raise RuntimeError(
            "Unified L3 V79 candidate registry validation failed: "
            + ",".join(missing)
        )

    _runtime_applied = True

    print(
        "TWINPANEL_UNIFIED_L3_CANDIDATE_REGISTRY_V79_ACTIVE "
        "source=transport_candidates.SPECS "
        f"candidates={','.join(sorted(SPECS))} "
        "agent_rollout_marker=v79",
        flush=True,
    )
