# TwinConnect iOS — local VPN engines

The dashboard, account/plan/traffic, and canonical 16-protocol catalog come
from the *same TwinPanel license-resolved panel* on Windows, Android and iOS.
The platform-specific VPN transport runs locally inside a signed iOS app
extension. A server having a config does **not** imply a working local engine.

## First transport: WireGuard

Source files:
- `ios_native/TwinConnectWireGuardEngine.swift`: WireGuardKit adapter with
  start/stop callbacks; reads config from a shared Keychain persistent
  reference and never puts private keys in `providerConfiguration`.
- `ios_native/PacketTunnelProvider.swift`: dispatches only the canonical
  `wireguard` protocol to the adapter; other protocols fail closed.
- `ios_native/TwinConnectIOSVpnBridge.swift`: Flutter capability probe and
  read-only Network Extension status. The status remains not-ready until
  an extension is provisioned, embedded, installed and verified.
- `lib/native_vpn_bridge.dart`: shared Android/Windows/iOS gate.
- `test/ios_wireguard_local_engine_contract_test.dart`: initial safety
  regression checks.

The checked-in adapter has an optional WireGuardKit compilation branch.
**The current simulator workflow type-checks the no-engine fallback.**
It does not bundle WireGuardKitGo or create a signed extension.

## Required device build (not done yet)

1. The generator `ios_native/install_packet_tunnel_target.rb` now creates
   the `PacketTunnel` extension target (bundle ID
   `com.twinpanel.twinconnect.PacketTunnel`) and embeds it into Runner.
   Its current WireGuard backend is a fail-closed fallback until linked.
2. Network Extensions and shared Keychain entitlement templates are now
   checked in for Runner and the extension. Configure *real* provisioning
   and Apple Developer signing for both bundle identifiers.
3. Integrate and link official [WireGuardKit and WireGuardKitGo from
   wireguard-apple](https://github.com/WireGuard/wireguard-apple) into the
   extension target, including the wg-quick parser model from that project,
   in accordance with its license.
4. Use a single shared Keychain access group to store the WireGuard
   configuration. The host app passes only a Keychain persistent reference
   using `NETunnelProviderProtocol.passwordReference`.
   `providerConfiguration` carries nonsecret `protocol=wireguard` only.
   Do not save a private key, PSK or full profile in preferences, logs or
   providerConfiguration.
5. Save and load an authorized `NETunnelProviderManager` for the correct
   tenant. Never accept cross-tenant session credentials.
6. Use `NETunnelProviderSession.startTunnel()`, observe status and counters,
   and verify handshakes, DNS and routes on a physical iPhone.
7. Only **after** runtime verification, change the native capability
   report to announce the supported protocol. Do not pretend WireGuard
   is available merely because the code type-checks.

## Other protocols

The remaining 15 protocol IDs stay visible in the shared panel catalog, but
they require platform-specific engines/adapters to operate on iOS. It is
incorrect to take a Windows EXE or an Android service and claim it operates
inside the iOS Network Extension. Modern protocols need an approved,
iOS-compatible packet transport integration, not a local proxy that silently
forwards unrelated system traffic.

## Testing boundaries

- GitHub Actions and Appetize: Flutter UI, catalog, integration-contract tests,
  Swift syntax/type checks, mock panels and simulator-only app.
- Real iOS VPN: requires signed embedded extension and a compatible physical
  iPhone/device cloud that permits VPN/Network Extensions.
- No tests or results may label a protocol `connected` or `ready` without
  verifiable native evidence.

## Host app start/stop (implemented but not yet device-ready)

- `lib/ios_wireguard_controller.dart` routes Flutter commands to iOS.
- `lib/live_dashboard.dart` keeps the original **Connect now** UI and
  fetches a fresh, authorized WireGuard profile from the owning panel
  via `ConnectionBootstrap` only after native capability checks.
- `ios_native/TwinConnectIOSVPNControl.swift` saves the single-node
  profile in a shared Keychain group, configures `NETunnelProviderManager`,
  and invokes `startVPNTunnel()` / `stopVPNTunnel()`.
- `ios_native/install_packet_tunnel_target.rb` builds an embedded Xcode
  app extension from the Flutter-generated `ios/` project.
- Native capability handshake is deliberately **not ready** until the
  upstream WireGuardKit plus its compiled Go backend are actually linked
  and a signed device build is verified. Simulator/Appetize does not prove
  any true VPN connection.
