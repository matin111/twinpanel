from __future__ import annotations

from . import transport_candidates as candidates
from .transport_candidates import tp6_fast


MARKER = "TWINPANEL_TP6_CANDIDATE_REGISTRY_V208"
TP6_FAST_SPEC = {
    "priority": 103,
    "label": "TP6 Fast",
    "family": "ipv6-kernel-l3",
}

# Linux evaluates lower RPDB priorities first. Keep the historical route-table
# namespace unchanged, but place the source-policy rule before the built-in
# `main` rule at priority 32766. The 900-slot range stays disjoint from TP27.
TP6_POLICY_TABLE_BASE = 34000
TP6_POLICY_RULE_BASE = 30000
TP6_POLICY_SPAN = 900
LINUX_MAIN_RULE_PRIORITY = 32766

_applied = False


def _tp6_runtime(tunnel_id: int) -> dict:
    return candidates._l3_runtime(
        tunnel_id=max(int(tunnel_id), 1),
        transport="tp6_fast",
        octet=249,
        interface_prefix="tp6",
        priority=int(TP6_FAST_SPEC["priority"]),
        port=None,
    )


def apply_tp6_candidate_registry_v208() -> None:
    """Add TP6 without rewriting the historical V202 registry source contract."""
    global _applied
    if _applied:
        return

    base_legacy_runtime = candidates._legacy_runtime
    base_legacy_policy_ids = candidates._legacy_policy_ids

    def legacy_runtime(name: str, tunnel_id: int) -> dict:
        value = str(name or "").strip().lower()
        if value == "tp6_fast":
            return _tp6_runtime(tunnel_id)
        return base_legacy_runtime(value, tunnel_id)

    def legacy_policy_ids(name: str, tunnel_id: int) -> tuple[int, int]:
        value = str(name or "").strip().lower()
        if value == "tp6_fast":
            offset = int(tunnel_id) % TP6_POLICY_SPAN
            table = TP6_POLICY_TABLE_BASE + offset
            priority = TP6_POLICY_RULE_BASE + offset
            return table, priority
        return base_legacy_policy_ids(value, tunnel_id)

    candidates._common.SPECS["tp6_fast"] = TP6_FAST_SPEC
    candidates.SPECS["tp6_fast"] = TP6_FAST_SPEC
    candidates.ACTIVE_SPECS["tp6_fast"] = TP6_FAST_SPEC
    candidates.INSTALLERS["tp6_fast"] = tp6_fast.install

    # Keep the original public runtime()/policy_ids() function objects intact because
    # API modules import them directly. Their fallback globals are replaced
    # in-place, so previously imported references gain TP6 support safely.
    candidates._legacy_runtime = legacy_runtime
    candidates._legacy_policy_ids = legacy_policy_ids

    _applied = True
    print(
        f"{MARKER}_ACTIVE "
        "candidate=tp6_fast "
        "outer=ipv6 "
        "inner=ipv4-private-l3 "
        "profiles=ip6gre,ipip6 "
        "auto_install=false",
        flush=True,
    )
