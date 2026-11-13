# TwinConnect Windows system-wide Kill Switch — design and release gates

Status: **native WFP preflight implemented; global enforcement NOT implemented, NOT enabled, NOT verified**.

## Intended behavior

Enabling this feature must protect *all outbound traffic*, regardless of whether the active protocol is WireGuard, OpenVPN, OpenConnect/Cisco, L2TP, Xray/sing-box, Sudoku or another transport. Full-system protection is an OS firewall task, not a Flutter preference or per-protocol checkbox.

**No release may display "Protected" until a separate privileged Windows service verifies that outbound IPv4 and IPv6 filtering is enforced.**

## Threat model

1. Tunnel dies or loses handshake, but the app remains open.
2. The Flutter app or transport process crashes.
3. User logs out, switches servers/protocols, or changes Wi-Fi.
4. PC sleeps, wakes, reboots or loses the network.
5. DNS outside the tunnel, IPv6, alternate NICs, or fallback/proxy routes leak.
6. Firewall/BFE service restarts, filters are removed or a third-party security product interferes.
7. UI requests disable or app uninstall fails halfway.
8. Administrative access is absent, endpoints rotate or split-tunneling exceptions conflict.

## Required architecture before arming

- Dedicated signed Windows service with authenticated local IPC, restricted permissions and a durable on/off state; it must survive Flutter termination.
- WFP provider/sublayer and transaction-managed, persistent filters with explicit ownership keys, applied for **both IPv4 and IPv6**. Persisted rules require a recovery strategy because they remain when the app crashes. A dynamic WFP session is suitable for a safe preflight, not a persistent crash-safe kill switch.
- Permit only authenticated transport egress to the verified VPN endpoint(s), with correct handling of bootstrap DNS, DHCP/NDP and loopback. Do not whitelist all traffic of the entire app or all DNS; do not allow untrusted interfaces by default.
- Traffic via the verified tunnel adapter must be separately permitted. Connections must not be declared protected simply because the interface is present; verify actual routes and filter state.
- During connect/switch/reconnect/disconnect, **install and confirm blocking before** a packet can escape. Never briefly disable the blocker to switch protocols.
- Stop, disable, uninstall and crash recovery must remove **only TwinConnect-owned rules**. Provide an independent, administrator-authorized emergency recovery tool that is installed alongside the service. Never advise disabling the entire Windows Firewall.
- Explicit modes: **Strict / Always-on** (block traffic even while VPN is intentionally disconnected) and optionally **Session-only** (restore normal connectivity on an intentional user disconnect), with clear user confirmation. Never silently infer one mode from the other.
- Native guard status: service installed/running, enabled, verified filters for v4 and v6, recovery mechanism healthy, active endpoint exceptions and applicable interfaces; status contract versioned. Never trust a saved setting as proof.
- Allow LAN and per-app exclusions only after separate policy audit; mutually incompatible configurations must fail closed.

## Current code additions

- `native/windows/twinconnect_global_killswitch.h`: read-only WFP engine preflight; adds **zero filters**.
- `tools/install_windows_native.py`: attaches `getGlobalKillSwitchStatus` to the existing native Flutter channel.
- `lib/native_vpn_bridge.dart`: versioned, conservative status decoding.
- `lib/vpn_settings.dart`: shows prerequisite and keeps the toggle locked until verified native enforcement.
- `test/windows_global_killswitch_contract_test.dart`: regression checks to prevent cosmetic or unsafe activation.

## Experimental WFP implementation (NOT production-ready)

`native/windows/twinconnect_global_guard_experimental.cpp` implements a
**separate opt-in prototype** that can transactionally add persistent IPv4
and IPv6 outbound-block filters and remove only its own rules. The requested
VPN tunnel alias is restricted to TwinConnect-owned adapters, and one numeric
IPv4 transport endpoint may be excluded. The emergency `disarm` operation is
a distinct administrator command. CI compiles this experiment but never runs,
packages, installs or arms it.

**Critical remaining requirements:** It has not been packet-capture tested;
IPv6 VPN transport endpoint exceptions, loopback proxy chains, DHCP/NDP,
reconnection, protocol-specific adapters, firewall arbitration, endpoint
rotation, Windows reboot boot-time coverage, and mandatory recovery testing
are not yet implemented or proven. Do not enable it on real user machines.

## Minimum Windows isolated-VM acceptance plan

1. Verify non-admin app cannot arm; no rules are written by the preflight.
2. Install signed service and ensure its recovery command is usable **before** activating any persistent rule.
3. With VPN disconnected, arm strict mode. Check outbound IPv4+IPv6 DNS/HTTPS/QUIC/UDP/ICMP and secondary adapters are blocked.
4. Connect each protocol: only verified VPN transport egress is allowed, and browser/app traffic uses the tunnel, including DNS and IPv6.
5. Kill each transport process and the Flutter process separately; verify no direct egress.
6. Change Wi-Fi, disable NIC, wake from sleep, switch nodes, lose endpoint DNS; verify no temporary leak.
7. Stop/restart BFE, restart the service, reboot and repeat; verify startup never opens an unintended leak window.
8. Disable feature and uninstall; verify removal of only owned filters and restoration of original network behavior, without affecting unrelated rules.
9. Verify rollback when WFP installation/verification partially fails. Include explicit emergency recovery test.
10. Block packaging/release unless firewall checks and recovery tests pass on real Windows with packet capture.

This design deliberately avoids enabling global firewall changes during normal app testing or on production VPN nodes.
