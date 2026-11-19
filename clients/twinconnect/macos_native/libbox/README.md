# Native Libbox bridge integration

Target: a **signed** macOS `NEPacketTunnelProvider`, not an external
sing-box command launched from a sandboxed Flutter Runner.

* Compile and verify upstream `Libbox.xcframework` for macOS using
  `twinconnect-macos-libbox-bridge-smoke.yml`.
* Link the macOS Libbox **static framework archive** into the **PacketTunnel**
  executable, not merely the host app. Official gomobile produces an
  architecture-specific static archive (including a `go.o` object inside
  `Libbox.framework/Libbox`); do **not** embed it as a runtime dylib.
  `otool -L PacketTunnel` therefore must **not** be used as proof of Libbox
  static linkage. Inspect `nm -g PacketTunnel` for the imported Libbox
  Objective-C/Go symbols (for example `_LibboxSetup` or
  `_OBJC_CLASS_$_Libbox...`), and separately validate signed egress.
  Do not run `install_name_tool` on the Go archive.
* Adapt `Libbox.PlatformInterface` and the required TUN descriptors,
  lifecycle, DNS, and default network monitoring to Apple's
  `NEPacketTunnelFlow`, as supported by libbox's Apple platform binding.
* Store account-scoped native outbound configuration in a signed,
  shared-Keychain access group; never place credentials in
  `NETunnelProviderProtocol.providerConfiguration` or build logs.
* Validate selected protocol and subscription entitlements before
  requesting secrets; never guess unprovisioned servers or inbound profiles.
* Apply full tunnel routes via `setTunnelNetworkSettings` only after
  successful engine setup; verify live egress/handshake separately.
* Add packet flow counters, disconnect/reconnect, and DNS leak tests on
  a **real signed macOS host** before setting `engineReady` to true.

The current standalone sing-box and Xray executables only provide
offline profile checks. They do not consume `NEPacketTunnelFlow`.
Until the bridge and signed entitlements exist, the existing fail-closed
runtime behavior must remain unchanged.
