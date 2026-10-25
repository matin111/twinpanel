from __future__ import annotations

from . import smart_transport_auto_v21 as smart
from . import tp27_reference_runtime_v91 as reference_v91
from . import transport_candidates as candidates
from .tp6_candidate_registry_v208 import apply_tp6_candidate_registry_v208
from .transport_candidates import kernel_ipip, kernel_vxlan


MARKER = "TWINPANEL_KERNEL_TRANSPORT_REGISTRY_V209"
KERNEL_IPIP_SPEC = {
    "priority": 107,
    "label": "Kernel IPIP",
    "family": "kernel-ipip-l3",
}
KERNEL_VXLAN_SPEC = {
    "priority": 108,
    "label": "Kernel VXLAN",
    "family": "kernel-vxlan-udp-l3",
}

_applied = False


def _kernel_ipip_runtime(tunnel_id: int) -> dict:
    return candidates._l3_runtime(
        tunnel_id=max(int(tunnel_id), 1),
        transport="kernel_ipip",
        octet=244,
        interface_prefix="tpip",
        priority=int(KERNEL_IPIP_SPEC["priority"]),
        port=None,
    )


def _kernel_vxlan_runtime(tunnel_id: int) -> dict:
    tid = max(int(tunnel_id), 1)
    return candidates._l3_runtime(
        tunnel_id=tid,
        transport="kernel_vxlan",
        octet=243,
        interface_prefix="tpvx",
        priority=int(KERNEL_VXLAN_SPEC["priority"]),
        port=37000 + (tid % 1000),
    )


def _ensure_smart_membership() -> None:
    # Explicit-install only: never expand AUTO_INSTALL_NAMES here.
    smart.CANDIDATE_NAMES = frozenset(
        (*smart.CANDIDATE_NAMES, "kernel_ipip", "kernel_vxlan")
    )
    smart.ALL_AUTO_NAMES = frozenset(
        (*smart.ALL_AUTO_NAMES, "kernel_ipip", "kernel_vxlan")
    )


def apply_kernel_transport_registry_v209() -> None:
    """Register explicit-install kernel IPIP/VXLAN candidates additively.

    The current TP27/Spoof policy remains authoritative. These lanes are never
    auto-installed; after an explicit successful install they participate in
    the existing health/stability/benchmark lifecycle and can then be selected
    manually or considered by Smart Auto like any other qualified candidate.
    """

    global _applied
    if _applied:
        return

    # TP6 is another additive candidate and its runtime wrapper must exist before
    # V209 extends the same fallback chain. This also fixes API processes that
    # previously never applied the TP6 registry used by the manager process.
    apply_tp6_candidate_registry_v208()

    base_legacy_runtime = candidates._legacy_runtime
    base_legacy_policy_ids = candidates._legacy_policy_ids

    def legacy_runtime(name: str, tunnel_id: int) -> dict:
        value = str(name or "").strip().lower()
        if value == "kernel_ipip":
            return _kernel_ipip_runtime(tunnel_id)
        if value == "kernel_vxlan":
            return _kernel_vxlan_runtime(tunnel_id)
        return base_legacy_runtime(value, tunnel_id)

    def legacy_policy_ids(name: str, tunnel_id: int) -> tuple[int, int]:
        value = str(name or "").strip().lower()
        if value == "kernel_ipip":
            table = 35000 + (int(tunnel_id) % 900)
            return table, table
        if value == "kernel_vxlan":
            table = 36000 + (int(tunnel_id) % 900)
            return table, table
        return base_legacy_policy_ids(value, tunnel_id)

    for name, spec, installer in (
        ("kernel_ipip", KERNEL_IPIP_SPEC, kernel_ipip.install),
        ("kernel_vxlan", KERNEL_VXLAN_SPEC, kernel_vxlan.install),
    ):
        candidates._common.SPECS[name] = spec
        candidates.SPECS[name] = spec
        candidates.ACTIVE_SPECS[name] = spec
        candidates.INSTALLERS[name] = installer

    # Keep the original public runtime()/policy_ids() function objects intact.
    # Their fallback globals are replaced in-place, matching the proven TP6
    # additive-registration pattern and preserving existing imports.
    candidates._legacy_runtime = legacy_runtime
    candidates._legacy_policy_ids = legacy_policy_ids

    _ensure_smart_membership()

    # V202 replaces the V91 activation hook with its final active policy. V91
    # reapplies that hook when its reconciler starts, so wrap the current hook
    # and restore V209 membership after every later V91 policy refresh.
    base_activate = reference_v91.activate_manager_candidate_policy_v91

    def activate_with_kernel_v209() -> None:
        base_activate()
        _ensure_smart_membership()

    reference_v91.activate_manager_candidate_policy_v91 = activate_with_kernel_v209

    _applied = True
    print(
        f"{MARKER}_ACTIVE "
        "candidates=kernel_ipip,kernel_vxlan "
        "install=explicit-only "
        "auto_install_unchanged=true "
        "encryption=none",
        flush=True,
    )
