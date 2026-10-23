from __future__ import annotations

# V207 is an additive overlay over the immutable rc.206 registry. Keeping the
# previous registry in its own module makes the IPv6 carrier easy to audit and
# rollback while preserving every existing TP27/Spoof/cleanup contract.
from . import registry_v206 as _base
from . import tp6_fast


TP6_FAST_SPEC = {
    "priority": 103,
    "label": "TP6 Fast",
    "family": "ipv6-kernel-l3",
}

_base._common.SPECS["tp6_fast"] = TP6_FAST_SPEC
_base.SPECS["tp6_fast"] = TP6_FAST_SPEC
_base.ACTIVE_SPECS["tp6_fast"] = TP6_FAST_SPEC
_base.INSTALLERS["tp6_fast"] = tp6_fast.install

_base_runtime = _base.runtime
_base_policy_ids = _base.policy_ids


def _tp6_fast_runtime(tunnel_id: int) -> dict:
    """IPv6 outer carrier with an isolated private IPv4 /30 inner L3 path."""
    return _base._l3_runtime(
        tunnel_id=max(int(tunnel_id), 1),
        transport="tp6_fast",
        octet=249,
        interface_prefix="tp6",
        priority=int(TP6_FAST_SPEC["priority"]),
        port=None,
    )


def runtime(name: str, tunnel_id: int) -> dict:
    value = str(name or "").strip().lower()
    if value == "tp6_fast":
        return _tp6_fast_runtime(tunnel_id)
    return _base_runtime(value, tunnel_id)


def policy_ids(name: str, tunnel_id: int) -> tuple[int, int]:
    value = str(name or "").strip().lower()
    if value == "tp6_fast":
        table = 34000 + (int(tunnel_id) % 900)
        return table, table
    return _base_policy_ids(value, tunnel_id)


# Make V207 runtime/policy authoritative for generic probe/uninstall paths.
_base.runtime = runtime
_base.policy_ids = policy_ids
_base._common.runtime = runtime
_base._common.policy_ids = policy_ids

# TP6 resolves runtime through common at call time; expose the wrapper here for
# callers that import it from the package contract.
tp6_fast.runtime = runtime

SPECS = _base.SPECS
ACTIVE_SPECS = _base.ACTIVE_SPECS
INSTALLERS = _base.INSTALLERS
catalog = _base.catalog
install_transport = _base.install_transport
uninstall_transport = _base.uninstall_transport
close_pair = _base.close_pair
connect_pair = _base.connect_pair
default_interface = _base.default_interface
mark = _base.mark


__all__ = [
    "SPECS",
    "ACTIVE_SPECS",
    "INSTALLERS",
    "TP6_FAST_SPEC",
    "catalog",
    "runtime",
    "policy_ids",
    "install_transport",
    "uninstall_transport",
    "close_pair",
    "connect_pair",
    "default_interface",
    "mark",
]
