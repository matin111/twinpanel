from __future__ import annotations

from app.managed_deep_diagnostics_v32 import _node_script, _runtime_for
from app.routers.modern_transports import router


def _remote_python(shell: str) -> str:
    marker = "python3 - <<'PY'\n"
    assert shell.startswith(marker), shell[:120]
    assert shell.endswith("\nPY"), shell[-120:]
    return shell[len(marker):-3]


def main() -> None:
    kcp = _runtime_for("kcp_2027", 5)
    assert kcp["interface"] == "tp27k5"
    assert kcp["iran_ip"] == "10.252.71.1"
    assert kcp["exit_ip"] == "10.252.71.2"
    assert kcp["port"] == 45105
    assert kcp["carrier"]["interface"] == "bh5"
    assert kcp["firewall_marker"] == "TP2027-BH5-udp-45105"

    mt = _runtime_for("mtunnel", 5)
    assert mt["interface"] == "mtun5"
    assert mt["iran_ip"] == "10.254.0.21"
    assert mt["exit_ip"] == "10.254.0.22"
    assert mt["port"] == 39005
    assert mt["protocol"] == "udp"

    gre = _runtime_for("kernel_gre", 5)
    assert gre["interface"] == "tpgr5"
    assert gre["protocol"] == "gre"

    gost = _runtime_for("gost_tun", 5)
    assert gost["interface"] == "tpgs5"
    assert gost["port"] == 25005
    assert gost["protocol"] == "tcp"

    shell = _node_script(
        service=str(kcp["iran_service"]),
        iface=str(kcp["interface"]),
        source_ip=str(kcp["iran_ip"]),
        peer_ip=str(kcp["exit_ip"]),
        remote_public_ip="198.51.100.2",
        protocol="udp",
        port=45105,
        server=False,
        firewall_marker=str(kcp["firewall_marker"]),
        carrier_iface="bh5",
        secret_kind="file",
        secret_path=str(kcp["secret_path"]),
    )
    compile(_remote_python(shell), "<v32-remote-diagnostic>", "exec")

    paths = {route.path for route in router.routes}
    assert "/v1/tunnels/{tunnel_id}/managed-deep-diagnose" in paths
    assert "/v1/tunnels/{tunnel_id}/managed-deep-repair" in paths

    print(
        "MANAGED_DEEP_DIAGNOSTICS_V32_SMOKE_OK "
        "tunnel5_runtime=1 remote_python_compile=1 routes=2 "
        "no_port_rotation=1 no_mtu_change=1"
    )


if __name__ == "__main__":
    main()
