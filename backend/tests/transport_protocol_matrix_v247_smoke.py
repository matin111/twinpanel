from __future__ import annotations

import inspect
from types import SimpleNamespace

from app import active_l3_route_binding_v94 as binding_v94
from app import protocol_dataplane_desired_state_v87 as protocol_v87
from app import smart_transport_auto_v21 as smart
from app import unified_l3_core_v49 as unified_v49
from app.kernel_transport_registry_v209 import apply_kernel_transport_registry_v209


EXPECTED_PROTOCOLS = {
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
    "v2ray",
}

ACCESS_PROTOCOLS = {
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
}


def main() -> None:
    # The desired-state layer must keep all production protocol families bound
    # to the logical L3 service plane. Xray/V2Ray is userspace on Exit, while
    # the other four also require Exit-side client-subnet forwarding/NAT.
    assert EXPECTED_PROTOCOLS.issubset(
        set(protocol_v87._PROTOCOL_ENABLE_ATTR)
    )
    assert set(protocol_v87._ACCESS_PROTOCOLS) == ACCESS_PROTOCOLS

    route_source = inspect.getsource(
        protocol_v87._service_routes_for_exit_v87
    )
    for protocol in ("cisco", "openvpn", "wireguard", "v2ray"):
        assert f'"{protocol}"' in route_source

    l2tp_source = inspect.getsource(
        protocol_v87._l2tp_routes_for_exit_v87
    )
    assert '"l2tp"' in l2tp_source
    assert "_L2TP_PUBLIC_PORTS" in l2tp_source

    # Unified L3 V49 must combine the normal service routes and L2TP into one
    # selected logical carrier. A failover therefore moves the service plane as
    # one unit instead of independently moving protocols.
    unified_source = inspect.getsource(
        unified_v49._service_routes_unified_v49
    )
    assert "_original_service_routes_for_exit" in unified_source
    assert "_original_l2tp_routes_for_exit" in unified_source
    assert 'route["core"] = "unified_l3_v49"' in unified_source

    # active_transport is the physical L3 authority. preferred/legacy values
    # are fallbacks only, so an installed VXLAN standby does not silently take
    # production traffic until selected by Manual/Smart Auto.
    fake = SimpleNamespace(
        active_transport="kernel_vxlan",
        preferred_transport="tp27_fast",
        transport="ssh_tun",
    )
    assert binding_v94._transport_name(fake) == "kernel_vxlan"

    fake.active_transport = None
    assert binding_v94._transport_name(fake) == "tp27_fast"

    # V209 owns additive kernel-candidate membership only. It deliberately does
    # not own/reset the baseline TP27 auto-install policy. Kernel candidates
    # must therefore become selectable/auto-eligible after explicit install and
    # qualification without ever being silently auto-installed by V209.
    apply_kernel_transport_registry_v209()

    for name in ("kernel_ipip", "kernel_vxlan"):
        assert name in smart.CANDIDATE_NAMES
        assert name in smart.ALL_AUTO_NAMES
        assert name not in smart.AUTO_INSTALL_NAMES

    print(
        "TWINPANEL_TRANSPORT_PROTOCOL_MATRIX_V247_SMOKE_OK "
        "protocols=cisco,openvpn,wireguard,l2tp,xray "
        "authority=active_transport "
        "standby=qualified-explicit-candidates"
    )


if __name__ == "__main__":
    main()
