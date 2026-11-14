# TwinConnect iOS simulator foundation

This branch starts the **iPhone client**, reusing the existing Flutter UI and the
licensed-panel API. It does not yet contain an iOS packet-tunnel engine.

## What GitHub Actions verifies
- Generate iOS Runner with `flutter create --platforms=ios --org com.twinpanel --project-name twinconnect .`
- Resolve Flutter packages and run analysis and unit/widget tests on macOS
- Compile an **unsigned simulator-only** `Runner.app`
- Boot an available iPhone Simulator, install the app and launch the bundle
- Upload `TwinConnect-iOS-Simulator-v0.1.0.zip`, checksum, and
  **four screenshots** of Connect, Locations, Settings and Account as a
  temporary GitHub Actions artifact. The simulator build uses the explicit
  offline-only `lib/ios_preview_main.dart` entry point with fictitious
  credentials and nodes; the signed-in production app still uses `main.dart`
  and the real panel after authentication.

The simulator ZIP **cannot** be installed on a physical iPhone and is **not**
an IPA or an App Store/TestFlight release.

## Current safety boundary
- Sign-in, language, panel/brand information and server inventory are Flutter
  features and can be tested without a real iPhone with test panel credentials.
  The authenticated iPhone layout receives real brand, inventory, quota and
  plan data through `TwinConnectIphoneShell`; the alternate simulator-only
  UI preview receives hard-coded mock values instead.
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
