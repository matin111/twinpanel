# TwinConnect iOS simulator foundation

This branch starts the **iPhone client**, reusing the existing Flutter UI and the
licensed-panel API. It does not yet contain an iOS packet-tunnel engine.

## What GitHub Actions verifies
- Generate iOS Runner with `flutter create --platforms=ios --org com.twinpanel --project-name twinconnect .`
- Resolve Flutter packages and run analysis and unit/widget tests on macOS
- Compile an **unsigned simulator-only** `Runner.app`
- Boot an available iPhone Simulator, install the app and launch the bundle
- Upload **four PNG screenshots only** of Connect, Locations, Settings
  and Account as a temporary GitHub Actions artifact, without executable
  payloads that can trigger download warnings in Windows browsers. The simulator build uses the explicit
  offline-only `lib/ios_preview_main.dart` entry point with fictitious
  credentials and nodes; the signed-in production app still uses `main.dart`
  and the real panel after authentication.

The screenshots are only a visual review artifact, not an IPA, an App
Store/TestFlight release, or an installable app for Windows or iPhone.

## Current safety boundary
- Sign-in, language, panel/brand information and server inventory are Flutter
  features and can be tested without a real iPhone with test panel credentials.
  All authenticated Windows, Android and iPhone clients use
  `TwinConnectLiveDashboard` with the **same** panel resolver, brand,
  catalog, inventory, quota and plan state. Compact Android and iOS layouts
  share bottom navigation while Windows retains desktop sidebar. The
  simulator-only entry point uses the same dashboard with isolated fictional
  fixture values; it never authenticates or contacts a panel.
- iOS VPN controls do not attempt Windows-only subprocesses, PowerShell or WFP.
- VPN connection is intentionally disabled on iOS until a signed iOS
  `NEPacketTunnelProvider` app extension and a suitable VPN engine exist.
- Real packet-tunnel connectivity, background behavior, leak prevention and
  protocol compatibility **require an actual iPhone** for final confirmation.
- Do not add `com.apple.developer.networking.networkextension` entitlements
  or claim working VPN access before Apple provisioning and engine integration.

## Next platform work
1. Add a real persistent `ios/` project and bundle identifiers for Runner and
   Packet Tunnel extension.
2. Create the Swift Network Extension bridge, with status and connection
   lifecycle semantics defined independently from Windows.
3. Integrate actual supported engines/profiles one protocol at a time.
4. Provision Apple Developer signing and a TestFlight beta; validate on an
   iPhone owned by a tester (not the developer necessarily).
5. Implement iOS platform-appropriate DNS, packet routing and reconnect
   behavior; desktop Windows Kill Switch/WFP logic is **not** reused on iOS.

The app remains closed-source by product intent. The source is currently
hosted in a public GitHub repository, which must be moved/restructured into a
private repository before claiming it is confidential.
