# TwinConnect macOS — unsigned standalone connection path

This is an **executable local-proxy development backend**, independent of
Apple's Network Extension. It does not create a system VPN, configure DNS,
install routes, or activate Kill Switch. Never label it as connected until a
real SOCKS/HTTP request through the proxy succeeds.


## AppKit Hysteria2 failure diagnostics

When a proxied HTTPS request fails, Quick Connect now displays **separate fixed,
redacted curl and sing-box diagnostic codes**, e.g. `PROXY_OR_REMOTE_TIMEOUT`,
`PROXY_TCP_UNREACHABLE`, or `PROXY_SOCKS_HANDSHAKE_FAILED` (curl error 97) instead
of an uninformative generic failure. Engine failures (e.g. `HYSTERIA2_REMOTE_AUTH_REJECTED`,
`ENGINE_REMOTE_TIMEOUT`, `ENGINE_REMOTE_TLS_CERTIFICATE_FAILURE`) may be classified
without printing remote addresses or passwords. Each new test truncates the
previous engine log so a stale error is not misattributed to a new server.
Curl error 97 alone does **not** establish whether SOCKS negotiation,
Hysteria2 authentication, or the remote transport caused the failure. The standalone CLI also
supports `python3 macos_native/standalone_connection_manager.py diagnose`.
Do not paste raw `engine.log` into chat or an issue; it can contain private
connection details. These codes are diagnostics, not proof of successful
handshake or VPN protection.

## AppKit cloud Mac: real Hysteria2 proxy test from selected account/server

The native Metal-free AppKit Locations screen receives live, authenticated
panel server and protocol lists. In Quick Connect, after selecting an
entitled Hysteria2 protocol and one of the assigned nodes, the **primary Test
Hysteria2 proxy** button requests a fresh protocol catalog,
assigned server inventory and exact node profile through the authenticated
native directory. The reviewed client outbound is executed as a private
loopback SOCKS proxy, probes HTTPS egress, and then the helper stops the
engine and deletes temporary credentials. The **primary** Quick Connect button is a one-request proxy test on this
unsigned cloud Mac, not a system VPN control. It guides the user to select
Hysteria2 and a server first. A signed system-wide PacketTunnel VPN is not
available in this unsigned build.
Only Hysteria2 is implemented in AppKit at this stage; the Flutter UI has
its own local-proxy test implementation. An installed engine alone is not
proof of a working network connection.

After pulling GitHub changes, recompile unsigned with
`bash tool/build_macos_unsigned_debug.sh` and relaunch the fresh Debug
app under Xcode DerivedData `Build/Products/Debug/twinconnect.app`
(not `Index.noindex/Build/Products`).

## TwinConnect Flutter login -> panel -> local proxy (development)

The macOS Flutter connection page now has a dedicated
`MacStandaloneConnectionCard` rather than rendering the Windows card.
It uses the already authenticated TwinPanel session to retrieve a **fresh**
protocol entitlement list, assigned server inventory and that exact node's
native profile. This is a separate development-only local SOCKS egress test;
it does not change the account, server routing, gateway or DNS.

The first in-app implementation covers `hysteria2`, `tuic`, `anytls`,
`naive`, `snell`, and `socks5`. V2Ray/Xray requires explicit inbound
variant selection; ShadowTLS requires a validated two-outbound chain.
Other engines remain unintegrated in the in-app test rather than
being falsely shown as connected.

The proxy runner expects binaries installed under
`~/twinpanel/clients/twinconnect/macos_native/build` on the development Mac.
It prepares a credential-bearing temporary config in a private system
temporary directory, starts only the matching preinstalled binary, makes
one HTTPS SOCKS request, and stops the process and deletes the temporary
config. Proxy egress success does **not** mean system VPN or Kill Switch
coverage. This Flutter path requires a working Flutter macOS renderer;
the separate AppKit fallback used by Metal-less cloud Macs is read-only.
macOS sandbox restrictions may prevent process spawning, which is shown
as an error rather than a fake successful connection.

To check the new Flutter code on the Mac:

```sh
cd ~/twinpanel/clients/twinconnect
flutter pub get
flutter test test/macos_standalone_panel_profile_test.dart
flutter test test/macos_standalone_ui_contract_test.dart
dart analyze lib/macos_standalone_panel_profile.dart \
  lib/macos_standalone_proxy_runtime.dart \
  lib/macos_standalone_connection_card.dart
```

## What is implemented

The central registry tracks 15 protocol codes:
`openvpn`, `openconnect`, `l2tp`, `wireguard`, `amneziawg`,
`v2ray`, `hysteria2`, `tuic`, `anytls`, `naive`, `shadowtls`,
`snell`, `socks5`, `mieru`, `trusttunnel`.

The unsigned local process backend can run a correctly installed Xray or
sing-box binary for **loopback SOCKS/HTTP/mixed proxy mode**, currently
`v2ray`, `hysteria2`, `tuic`, `anytls`, `naive`, `shadowtls`,
`snell`, and `socks5`. Other engines fail explicitly as not integrated.
Some upstream protocol support depends on the exact sing-box build and may
be rejected by that binary. The manager does not claim a handshake or
internet access from mere process startup.

## Run on a macOS development host

```sh
cd ~/twinpanel/clients/twinconnect
python3 macos_native/standalone_connection_manager.py list
python3 -m unittest -v macos_native/test_standalone_connection_manager.py
```

## Prepare an existing profile without editing server credentials

For Xray or sing-box **client JSON** (not the server-side inbound
configuration), the preparation tool strips the old TUN inbound, system DNS
and routing rules, creates a private per-request loopback SOCKS/mixed
profile, and leaves remote outbounds, secrets, TLS and transport data intact.
Do not paste client secrets into chat or GitHub issues.

```sh
python3 macos_native/prepare_standalone_profile.py \
  hysteria2 /path/to/private-existing-client.json --port 10808
```

The command prints a **local prepared JSON path**. Use that returned path
to start the matching engine (never commit that private file):

```sh
python3 macos_native/standalone_connection_manager.py \
  start hysteria2 '/Users/macvps/Library/Application Support/TwinConnect/standalone/prepared/YOUR_GENERATED_FILE.json'
python3 macos_native/standalone_connection_manager.py probe
python3 macos_native/standalone_connection_manager.py stop
```

Supported preparation protocol codes are `v2ray`, `hysteria2`,
`tuic`, `anytls`, `naive`, `shadowtls`, `snell`, `socks5`.
The selected outbound must be explicitly tagged in sing-box. ShadowTLS
requires its paired Shadowsocks outbound using `detour`. The generated
minimal routing deliberately selects the matching remote outbound,
rather than a direct outbound. Some profiles need additional DNS or
routing options and can be rejected by the native engine: fix these in
the **test copy**, not the existing account configuration.

This verifies only the selected application's proxied HTTPS request.
Other macOS apps remain on the original network route.

Install the required engine binary using the existing repository tooling.
Pass a **local file on disk**, containing the actual account's JSON config,
with **exactly one** loopback SOCKS, HTTP or mixed inbound, and an outbound
matching the requested protocol.

```sh
python3 macos_native/standalone_connection_manager.py start v2ray /path/to/local-xray-socks.json
python3 macos_native/standalone_connection_manager.py status
python3 macos_native/standalone_connection_manager.py probe
python3 macos_native/standalone_connection_manager.py probe --expected-ip 203.0.113.12
python3 macos_native/standalone_connection_manager.py stop
```

Replace 203.0.113.12 with the expected real public server exit IP before running the expected-IP probe. A response from the proxy test
must be checked against the expected egress; process_running_unverified
does **not** imply that a remote server was reached.

The state is kept in
`~/Library/Application Support/TwinConnect/standalone/` with user-only
permissions. The manager will never print config contents or secrets.
Do not paste actual client configurations into public issues or CI logs.
Only one managed engine can run at a time. The app's Flutter buttons are
**not yet connected** to this standalone process manager.


## One-command real egress smoke test (recommended)

With an **existing private client JSON** locally on the Mac, test a single
protocol through its loopback proxy without changing macOS routing:

```sh
python3 macos_native/smoke_test_standalone_proxy.py \
  hysteria2 "/absolute/path/to/private-client.json"
```

The runner creates a private transformed profile, starts the native engine,
makes an HTTPS request **through SOCKS5**, reports the public exit IP, then
stops the managed engine and deletes the temporary credential-bearing profile
even if the probe raises an error. It will refuse to start if another managed
engine is already running. A `test_passed` response means proxied egress was
reachable, **not** that macOS is connected system-wide.

For a known exit IP, use `--expected-ip IP`. Do not put a secret or
subscription URL into the command; pass the path of a client JSON file.
Do not use a server inbound configuration. The path may contain spaces,
so quote it. This script **does not** fetch credentials from the panel.
For servers with a dynamic exit IP, omit `--expected-ip`.

## Remote Mac safety

Keep the macOS server's original default route (for example `en0`)
untouched. In particular, do not load a full-tunnel `tun` inbound into
this manager. Even on unsigned macOS, privileged network setup needs
a separate deliberately audited helper. The Xcode PacketTunnel path remains
separate and requires valid signing/entitlements.

## Next implementation work

Implement the authenticated native desktop service/IPC boundary with
per-user process ownership, verified traffic statistics and safe stop,
then add the remaining protocol-specific engines. No Apple paid developer
membership is needed to exercise the loopback local-proxy path.
