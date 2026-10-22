from __future__ import annotations

import ast
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
TP27 = BACKEND / "app" / "transport_candidates" / "tp27_fast.py"
REGISTRY = BACKEND / "app" / "transport_candidates" / "__init__.py"
RUNTIME = BACKEND / "app" / "tp27_reference_runtime_v91.py"
POLICY = BACKEND / "app" / "spoof_candidate_policy_v202.py"
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
    policy = read(POLICY)
    manager = read(MANAGER)
    orphan = read(ORPHAN)
    tunnels = read(TUNNELS)
    provision = read(PROVISION)

    # TP27-core carrier contract remains byte-for-byte owned by tp27_fast.py:
    # in-kernel keyed Raw GRE first, then bounded GRE/FoU fallback.
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

    # V202 adds exactly one production candidate beside TP27 Fast. Historical
    # candidates remain source/runtime-known only for official cleanup.
    assert '"tp27_fast": TP27_SPEC' in registry
    assert '"spoof_wg": SPOOF_WG_SPEC' in registry
    assert '"kernel_gre": _LEGACY_SPECS["kernel_gre"]' in registry

    active_block = registry.split("ACTIVE_SPECS =", 1)[1].split("_legacy_runtime", 1)[0]
    assert '"tp27_fast"' in active_block
    assert '"spoof_wg"' in active_block
    for retired in (
        "kernel_gre",
        "tp27_masque",
        "tp27_tcp_direct",
        "gost_tun",
        "amneziawg",
        "netrix",
    ):
        assert f'"{retired}"' not in active_block

    installer_block = registry.split("INSTALLERS =", 1)[1].split("async def install_transport", 1)[0]
    assert '"tp27_fast": tp27_fast.install' in installer_block
    assert '"spoof_wg": spoof_wg.install' in installer_block
    for retired in (
        "kernel_gre",
        "tp27_masque",
        "tp27_tcp_direct",
        "gost_tun",
        "amneziawg",
        "netrix",
    ):
        assert f'"{retired}"' not in installer_block

    # TP27 Fast keeps the exact V91 10.253/16 runtime and dedicated policy
    # table. V202's generic helper only expresses that same established shape.
    assert "octet=253" in registry
    assert 'interface_prefix="tp27"' in registry
    assert "table = 29000 + (int(tunnel_id) % 900)" in registry

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

    # Existing provisioners still bind the supplied port directly; V91 changes
    # their requested port rather than adding another translation layer.
    assert "tcp-port = {port}" in provision
    assert "udp-port = {port}" in provision
    assert "config = f'''port {port}" in provision
    assert "ListenPort = {port}" in provision

    for token in (
        '"cisco": 20000',
        '"openvpn": 21000',
        '"wireguard": 22000',
    ):
        assert token in tunnels, token

    # V91 cleanup remains make-before-break: retired rows are removed only after
    # TP27 Fast is the active, enabled and online production carrier.
    assert 'if active != "tp27_fast":' in runtime
    assert 'TunnelTransport.transport == "tp27_fast"' in runtime
    assert '!= "online"' in runtime
    for retired in ("gost_tun", "amneziawg", "netrix", "kernel_gre"):
        assert f'"{retired}"' in runtime

    # V202 extends that same proven cleanup contract to the failed experimental
    # lanes while keeping TP27 Fast as the only automatic installer.
    assert 'smart.AUTO_INSTALL_NAMES = ("tp27_fast",)' in policy
    assert 'ACTIVE = frozenset({"tp27_fast", "spoof_wg"})' in policy
    for retired in ("tp27_masque", "tp27_mieru_tcp", "tp27_tcp_direct"):
        assert f'"{retired}"' in policy
    assert "reference_v91.RETIRED_CANDIDATES = tuple(retired)" in policy

    assert "tp27_reference_loop" in manager
    assert "twinpanel-tp27-reference-v91" in manager
    assert "runtime_reconciler_v4" in manager
    assert "spoof_candidate_policy=v202-final-active-set" in manager
    assert "active_candidates=tp27_fast,spoof_wg" in manager

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

    print("TP27_FAST_PRESERVE_PORT_V91_V202_OK")


if __name__ == "__main__":
    main()
