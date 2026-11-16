# TwinConnect macOS — signed Hysteria2 test candidate

The normal macOS GitHub Actions preview is unsigned. It deliberately **does
not** enable macOS VPN and must never report connected traffic. The separate
Libbox smoke build only tests the native Swift/Go link.

For a **developer-controlled cloud Mac** with an Apple Development certificate
and Network Extension capability provisioned to both app and extension:

1. Check out `feat/twinconnect-macos-packet-tunnel-foundation-20261116` and
   enter `clients/twinconnect`. Install Flutter, Xcode 16+, Go 1.25.5, the
   `xcodeproj` Ruby gem and `gomobile`/`gobind` v0.1.12.
2. Build the official sing-box **v1.14.4** `Libbox.xcframework` for macOS
   with `go run ./cmd/internal/build_libbox -target apple -platform macos`.
   Copy its full directory into
   `macos_native/build/libbox/Libbox.xcframework`. Do not substitute a
   standalone `sing-box` CLI for Libbox.
3. Generate and link the Flutter app and extension:

   ```bash
   flutter create --platforms=macos --org com.twinpanel --project-name twinconnect .
   python3 macos_native/install_macos_bridge.py
   ruby macos_native/install_packet_tunnel_target.rb
   ruby macos_native/libbox/link_libbox_packet_tunnel.rb
   ```

4. After Apple has provisioned `packet-tunnel-provider`, opt in **locally**
   with your own Team ID. This command modifies generated files in the local
   checkout; it does not submit Apple certificates or credentials to GitHub.

   ```bash
   export TWINCONNECT_APPLE_TEAM_ID=YOURTEAMID
   export TWINCONNECT_ENABLE_SIGNED_LIBBOX_TEST=YES
   python3 macos_native/prepare_signed_macos_candidate.py
   ```

5. Build using an actual development provisioning team and the explicit
   test-only Swift condition:

   ```bash
   xcodebuild -project macos/Runner.xcodeproj -scheme Runner \
     -configuration Debug -destination 'platform=macOS' \
     DEVELOPMENT_TEAM="$TWINCONNECT_APPLE_TEAM_ID" \
     SWIFT_ACTIVE_COMPILATION_CONDITIONS='TWINCONNECT_SIGNED_LIBBOX' \
     CODE_SIGNING_ALLOWED=YES build
   ```

6. Verify the app, PacketTunnel.appex and embedded Libbox.framework signatures
   with `codesign --verify --deep --strict`. Inspect app and extension
   entitlements with `codesign -d --entitlements :-`. A build can be green
   while provisioning, app-group access or Network Extension installation
   still fails at runtime.

**Required live acceptance tests** with a valid, entitled *test* subscription:
select the exact Hysteria2 node, verify status transitions, obtain a
nonzero network byte count and validated egress IP, check DNS and IPv6 leaks,
disconnect/reconnect and force failures (bad credentials, revoked profile,
unreachable endpoint, app exit). No failure may leave a green Connected badge
or direct-egress path.

The signed-build flag never enables itself in ordinary unsigned previews.
A working macOS extension, accepted OS startup, and a verified Hysteria2
peer handshake are three separate states. The current implementation makes
no claim that the last two have passed.
