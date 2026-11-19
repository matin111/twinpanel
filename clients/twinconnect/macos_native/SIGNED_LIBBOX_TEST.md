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
   xcodebuild -workspace macos/Runner.xcworkspace -scheme Runner \
     -configuration Debug -destination 'platform=macOS' \
     DEVELOPMENT_TEAM="$TWINCONNECT_APPLE_TEAM_ID" \
     SWIFT_ACTIVE_COMPILATION_CONDITIONS='TWINCONNECT_SIGNED_LIBBOX' \
     CODE_SIGNING_ALLOWED=YES build
   ```

6. Verify that the built application, embedded PacketTunnel.appex,
   and Libbox.framework are signed with the **same real Apple Team**, that the
   extension backend marker is enabled, and that the **effective** (signed)
   Network Extension and Keychain entitlements match. The verification command
   fails closed with an actionable reason:

   ```bash
   python3 macos_native/verify_signed_macos_bundle.py \
     build/macos/Build/Products/Debug/twinconnect.app
   ```

   If your signed candidate is at a different path, substitute that exact
   `.app` path. Do not copy the GitHub *unsigned* artifact to a Mac and expect
   the VPN to work: rebuild with your own Apple identity, marker and signing
   settings. A green Xcode build alone does not establish VPN functionality.

7. Run a real Hysteria2 test connection and record **live** connection
   state, handshake or endpoint reachability, IP change, packet counters,
   default route, DNS and IPv6. The verifier checks signing only.

## NaiveProxy (Apple/macOS) compatibility

NaiveProxy outbound is supported by sing-box **v1.14.4** only in builds
compiled with `with_naive_outbound` and its Cronet dependency. The
pinned official Apple `build_libbox` script enables this tag. The macOS
preview CI also requires the `with_naive_outbound` tag in the official
macOS CLI and verifies a synthetic Naive config with `sing-box check`.

The Naive profile requires the subscription's real `username`,
`password`, endpoint and validated TLS server name. Concurrent Naive
sessions above zero, TLS verification bypass, and untrusted route/DNS
overrides are rejected. QUIC and UDP-over-TCP are **not** invented: they
are used only if explicitly present and valid in the provider's profile.
A server that does not support UDP-over-TCP may not carry UDP traffic.
A green parser or unsigned build does not prove a usable full VPN.

Before marking Naive connected on an actual signed Mac, verify that
the endpoint authenticates, TCP and UDP traffic behave according to
the provisioned server's capabilities, the egress IP changes as
expected, DNS does not leak, and disconnect does not leave direct traffic.

## Local network evidence (signed cloud Mac only)

The following workflow records two local snapshots without uploading account
profiles or keys. Only `--probe-egress` contacts the public HTTPS IPv4 test
service. These files contain sensitive network information; **do not upload**
them to GitHub Actions or share them publicly.

```bash
python3 macos_native/capture_hysteria2_network_evidence.py sample \
  --phase baseline --output /tmp/twin-before.json --probe-egress
# Sign, install and start Hysteria2 from the actual TwinConnect app.
python3 macos_native/capture_hysteria2_network_evidence.py sample \
  --phase connected --output /tmp/twin-after.json --probe-egress
python3 macos_native/capture_hysteria2_network_evidence.py compare \
  --before /tmp/twin-before.json --after /tmp/twin-after.json
```

The tool captures only OS interfaces, route interface, a hash of the DNS
configuration, and an optional public IPv4. A changed IPv4 or new utun interface
is **supporting evidence, not proof** of a successful Hysteria2 handshake, DNS
leak protection, or fail-closed behavior. These still require live independent
verification on the signed Mac.

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

## Preflight before spending time on a cloud macOS host

Run this read-only diagnostic **before** building Flutter or provisioning the
PacketTunnel extension:

```bash
cd clients/twinconnect
python3 macos_native/preflight_macos.py
python3 macos_native/preflight_macos.py --json
python3 -m unittest macos_native/test_preflight_macos.py
```

A Mac can compile `Runner` and `Libbox.xcframework` successfully yet be
**unable to render Flutter**, particularly in some remote and virtualized graphics environments. Runtime messages such as `Could not acquire Metal device` and
`Unable to create FlutterView` show Flutter engine graphics initialization
failed; this does not establish whether Swift Metal API access works in the
same session. A positive Swift Metal probe **does not prove** the Runner can
render. Investigate the VM display/graphics path and Runner context before
asserting that host Metal is absent. A GUI preview must be validated by actual Runner rendering, not by a probe alone.

`xcodebuild ... CODE_SIGNING_ALLOWED=NO` is a **compile-only check**. The
generated unsigned app may not run a PacketTunnel extension. A development
certificate alone is insufficient: the app and extension both require
effective Network Extension provisioning, signing, and actual OS permission.
Do not conflate successful code compilation, an accepted tunnel start, and
confirmed encrypted network egress. Keep the fail-closed VPN behavior.

The preflight checks only the host. It deliberately does not read profiles,
VPN credentials, Apple Team IDs, certificates, or customer data. If signing
identities exist, it reports only their count; it cannot certify entitlement
approval or successful VPN traffic.
