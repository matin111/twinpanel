# TwinConnect macOS — unsigned standalone connection path

This is an **executable local-proxy development backend**, independent of
Apple's Network Extension. It does not create a system VPN, configure DNS,
install routes, or activate Kill Switch. Never label it as connected until a
real SOCKS/HTTP request through the proxy succeeds.

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
