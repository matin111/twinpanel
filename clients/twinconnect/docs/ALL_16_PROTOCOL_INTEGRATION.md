# TwinConnect — 16-protocol integration contract

Status: **all 16 registered in client and backend**, with account-scoped catalog and profile APIs. **No active native VPN engines are installed by this PR.**

## Protocols and engine families

| Protocol | Native integration family | Existing profile |
| --- | --- | --- |
| Cisco / OpenConnect | vetted OpenConnect native core | server, account, password |
| OpenVPN | OpenVPN native library | OVPN file and certificates |
| WireGuard | WireGuard native tunnel | WG .conf |
| L2TP/IPsec | supported OS-native VPN API | account, password, PSK |
| V2Ray / Xray | Xray native core | complete nested profiles: WebSocket TLS, XHTTP Reality, TCP |
| Hysteria2 | sing-box | QUIC / outbound |
| TUIC | sing-box | QUIC / outbound |
| AnyTLS | sing-box | TLS outbound |
| NaiveProxy | sing-box with Naive support enabled | Naive outbound |
| ShadowTLS | sing-box | preserve Shadowsocks to ShadowTLS detour chain |
| Snell | sing-box compatible core | outbound |
| SOCKS5 | sing-box / tun2socks | SOCKS5 with authentication; not encrypted by itself |
| Mieru | Mieru native core | Mieru profile |
| TrustTunnel | TrustTunnel native core | TrustTunnel profile |
| AmneziaWG | AmneziaWG native core | AWG-specific .conf (not ordinary WireGuard) |
| Sudoku | Sudoku native core | Sudoku profile |

No gRPC mode is added. Distinct Xray transports must not be reduced to one synthetic profile. Do not blindly convert AmneziaWG to WireGuard or flatten the ShadowTLS chain.

## API and security

The owning panel, rather than the central vendor, serves:
- POST /v1/central-app/public/protocols: 16-item read-only catalog with selected and config-record-present states, no credentials and no false native readiness.
- POST /v1/central-app/public/profiles: only one selected protocol's customer-safe existing connection items, requiring account username and subscription share token to agree with the same active subscription. Response is HTTPS only, private/no-store, at most 1 MiB.

The V2Ray feed uses the existing customer-safe Xray projection and preserves the distinct inbounds. The other feeds reuse live endpoint and credential projection. The new API does not provision or modify any servers, ports, SNI, keys, subscriptions or quota.

Flutter displays all 16 protocols and checks an independent versioned native handshake. It **does not fetch secret profiles when the native engine is unavailable**. Native credentials must never be sent to the vendor directory, persisted in SharedPreferences, sent to analytics or logged.

## Production release gates

1. Native tunnel integration per OS: Android VpnService; Windows protected service; iOS/macOS Network Extension with approved entitlements.
2. Version-pin, audit and integrate the actual protocol engine families listed above. Validate protocol-specific schemas and cryptographic settings.
3. Verify native capabilities, then pass fetched profiles directly to the relevant OS-native process in protected memory. Implement lifecycle, connection state, cancellation and crash recovery.
4. Enforce DNS/IPv6 and Kill Switch policies before advertising a connection as protected. Test leak behavior after Wi-Fi switching, app termination, reboot and disconnect.
5. End-to-end real-device tests for each of 16 protocols on each supported operating system. Explicitly mark unsupported protocol/OS combinations.
6. Sign distribution artifacts and review licensing, Apple VPN entitlements, privacy and marketplace requirements.
7. Merge dependent vendor licensing, registry, panel bridge and client PRs in order, with test/rollback evidence.

This branch is a safe protocol contract and data-path milestone, not a completed all-protocol VPN application.
