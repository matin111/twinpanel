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

## Linked device extension laboratory

Run bash tool/link_ios_wireguard_device_lab.sh after the ARM64 Go archive
build. It builds the pinned WireGuardKit Swift/C sources, adds the original
upstream wg-quick parser, and links the real adapter branch into a standalone
unsigned iOS ARM64 PacketTunnel.appex under build/ios-wireguard-lab/iphoneos.
The lab bundle is not embedded in Runner and has no Apple provisioning.
The capability marker stays false. Go runtime patch compatibility and
on-device packet delivery still require validation.

## Generated Xcode target integration

After the device library link succeeds, run
ruby tool/install_ios_wireguard_xcode_lab.rb in the isolated checkout.
It configures the existing PacketTunnel target in Runner.xcodeproj to link
the tested device archives and upstream profile parser for iphoneos only.
The simulator target retains the explicit no-engine fallback.
The generated project is machine-local and must not be committed with
absolute developer paths, cache artifacts or signing identities.

Validation: build the PacketTunnel target for iphoneos and iphonesimulator
with CODE_SIGNING_ALLOWED=NO and CODE_SIGNING_REQUIRED=NO; check wgTurnOn,
wgTurnOff and wgGetConfig in the device binary. For simulator, verify that
the device-only symbols are absent. This is build validation, not proof of
a working VPN on an iPhone. Runner remains fail-closed until a complete
signed-device runtime test verifies the actual transport.

## Debug-only CocoaPods recovery

If the iOS debug engine is present but profile/release downloads are blocked,
the generated SwiftPM FlutterFramework placeholder may leave plugins unable
to import Flutter on target-only builds. The generated project also needs
CocoaPods for flutter_secure_storage. The opt-in script
tool/prepare_ios_debug_cocoapods_lab.sh switches only the generated lab iOS
plugin integration to CocoaPods, with Debug settings using the real cached
Flutter engine. It does not patch the global Flutter SDK or the macOS project.
Run only after Flutter has generated its package metadata and Podfile.
Build the Pods-Runner target for the device Debug SDK without signing.
Do not use these generated settings for Release/Profile; restore the normal
Flutter-generated integration when the full SDK cache is available.
The full Runner still needs its Dart asset build and the simulator needs
its own installed runtime; native module compilation alone is not a full app.
