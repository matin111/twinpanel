# TwinConnect unsigned iOS laboratory

This is a separate worktree and feature branch, not a macOS VPN release.
The purpose is to test the application and portable VPN engines without
Apple signing or changing system routes, PF, DNS, or other production services.

## Reproduce

Prerequisites: Flutter, Xcode with iOS SDK, Ruby xcodeproj, Go, cached pinned
WireGuard dependencies, and an independently installed iOS Simulator runtime.

1. Run bash tool/prepare_ios_unsigned_lab.sh to generate Runner, register the
   existing native channel and embedded extension, remove any machine-specific
   signing team, and type-check the current fail-closed adapter for both SDKs.
2. Run bash tool/test_ios_wireguard_unsigned_lab.sh /path/to/wireguard-apple
   to execute the pinned upstream WireGuard real-UDP, two-peer, bidirectional
   packet test through in-memory ChannelTUNs. Test keys are ephemeral.
3. Run bash tool/build_ios_wireguard_archive_lab.sh /path/to/wireguard-apple
   to attempt a device ARM64 C archive build. This is a lab artifact only,
   not a signed or runtime-verified WireGuardKit integration.
4. Prepare iOS Flutter artifacts (flutter precache --ios, flutter pub get).
   Build UI using flutter build ios --simulator --debug --no-codesign.
   For an offline fixture UI use --target lib/ios_preview_main.dart.
5. Install a compatible iOS Simulator runtime and boot a simulator to test
   the actual application. No device installation is possible without signing.
6. Build the device app (flutter build ios --release --no-codesign) only
   after the compatible engines and iOS linking are implemented.

## Evidence boundary

- Swift typecheck currently exercises the no-engine branch. Do not mistake it
  for a linked WireGuard engine.
- WireGuard loopback exercises real encryption and IP packets over local UDP,
  not TwinPanel server credentials, iPhone system-wide routes or DNS.
- The C archive uses the pinned upstream source with the installed Go version.
  Upstream's historical runtime patch has not been validated on this Go release.
- Keep the production capability bridge fail-closed until real device evidence
  exists. No mock VPN success should appear in the production application.
- Actual signed Network Extension behavior, background transitions and
  system-level leak prevention require final device testing.
