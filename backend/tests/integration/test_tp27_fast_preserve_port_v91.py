from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
TP27 = BACKEND / "app" / "transport_candidates" / "tp27_fast.py"
REGISTRY = BACKEND / "app" / "transport_candidates" / "__init__.py"
RUNTIME = BACKEND / "app" / "tp27_reference_runtime_v91.py"
MANAGER = BACKEND / "app" / "tunnel_transport_manager_v12.py"
ORPHAN = BACKEND / "app" / "runtime_reconciler_v4.py"
TUNNELS = BACKEND / "app" / "routers" / "tunnels.py"
PROVISION = BACKEND / "app" / "routers" / "provision.py"


def read(path: Path) -> str:
    value = path.read_text(encoding="utf-8")
    ast.parse(value)
    return value


def main() -> None:
    tp27 = read(TP27)
    registry = read(REGISTRY)
    runtime = read(RUNTIME)
    manager = read(MANAGER)
    orphan = read(ORPHAN)
    tunnels = read(TUNNELS)
    provision = read(PROVISION)

    # TP27-core carrier contract: in-kernel keyed Raw GRE first, then bounded
    # GRE/FoU fallback. Both profiles remain one logical candidate.
    for token in (
        'NAME = "tp27_fast"',
        "MTU = 1400",
        "TXQUEUELEN = 1000",
        "FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)",
        'profile="gre-native"',
        'profile="gre-fou"',
        "mode gre local",
        "ttl 255 key",
        "encap fou encap-sport auto encap-dport",
        '"source": "matin111/tp27-core"',
        "await probe(",
    ):
        assert token in tp27, token

    # New product surface contains TP27. Legacy GRE remains health-visible only
    # for make-before-break and is not in ACTIVE_SPECS/installers.
    assert '"tp27_fast": TP27_SPEC' in registry
    assert '"kernel_gre": _LEGACY_SPECS["kernel_gre"]' in registry
    active_block = registry.split("ACTIVE_SPECS =", 1)[1].split("_legacy_runtime", 1)[0]
    assert '"tp27_fast"' in active_block
    assert '"kernel_gre"' not in active_block
    installer_block = registry.split("INSTALLERS =", 1)[1].split("async def install_transport", 1)[0]
    assert '"tp27_fast": tp27_fast.install' in installer_block
    for retired in ("gost_tun", "amneziawg", "netrix", "kernel_gre"):
        assert f'"{retired}"' not in installer_block

    # Dedicated policy table avoids collision with live kernel_gre during
    # make-before-break migration.
    assert "table = 29000 + (int(tunnel_id) % 900)" in registry
    assert '"network": f"10.253.' in registry

    # Preserve-port is the critical production fix: customer ingress port and
    # Exit service listener must be identical for Cisco DTLS, OpenVPN and WG.
    for token in (
        '"cisco": 20000',
        '"openvpn": 21000',
        '"wireguard": 22000',
        'settings.cisco_port = preserved_port(node.id, "cisco")',
        'settings.openvpn_port = preserved_port(node.id, "openvpn")',
        'settings.wireguard_port = preserved_port(node.id, "wireguard")',
        "install_l2tp=False",
        "install_v2ray=False",
        "xray=unchanged",
    ):
        assert token in runtime, token

    # Existing provisioners already bind the supplied port directly; V91
    # changes their requested port rather than adding another translation layer.
    assert "tcp-port = {port}" in provision
    assert "udp-port = {port}" in provision
    assert "config = f'''port {port}" in provision
    assert "ListenPort = {port}" in provision

    # Public endpoint plan is unchanged: preserve-port keeps the customer URLs
    # stable while moving the Exit listeners to those exact ports.
    for token in (
        '"cisco": 20000',
        '"openvpn": 21000',
        '"wireguard": 22000',
    ):
        assert token in tunnels, token

    # Retired candidates are deleted only after TP27 itself is online and is
    # the active carrier. This is the make-before-break safety gate.
    assert 'if active != "tp27_fast":' in runtime
    assert 'TunnelTransport.transport == "tp27_fast"' in runtime
    assert '!= "online"' in runtime
    for retired in ("gost_tun", "amneziawg", "netrix", "kernel_gre"):
        assert f'"{retired}"' in runtime

    # SmartAuto installs only TP27 after manager activation; selection scoring
    # constants are intentionally not changed here.
    assert 'smart.AUTO_INSTALL_NAMES = ("tp27_fast",)' in runtime
    assert "tp27_reference_loop" in manager
    assert "twinpanel-tp27-reference-v91" in manager
    assert "runtime_reconciler_v4" in manager

    # DB-authoritative orphan cleanup owns TP27 services/interface/routing and
    # never performs global firewall flushes.
    assert "twinpanel-tp27_fast-" in orphan
    assert "29000 + (tid % 900)" in orphan
    assert "TwinPanel-TP27-" in orphan
    for forbidden in (
        "iptables -F",
        "iptables -t nat -F",
        "iptables -t filter -F",
        "netfilter-persistent save",
    ):
        assert forbidden not in orphan
        assert forbidden not in registry

    print("TP27_FAST_PRESERVE_PORT_V91_OK")


if __name__ == "__main__":
    main()
