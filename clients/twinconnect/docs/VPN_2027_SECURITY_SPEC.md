# TwinConnect VPN security & 2027 capabilities

Status: architecture, native capability contract, bilingual configuration UI and tests. **No active VPN tunnel, OS firewall or kill switch is installed by this change.**

## One shared app for every licensed panel

The same Android, Windows, iOS, and macOS builds serve all panel owners and resellers. Brand and subscription/contact details are loaded from the tenant panel. Desired VPN routing policy is stored separately per customer account. The vendor directory never receives VPN usernames, passwords, share tokens, keys or configurations.

## Platform feature matrix

| Capability | Android | Windows | iOS consumer | macOS consumer |
| --- | --- | --- | --- | --- |
| Device-wide VPN | Native VpnService, IPv4 and IPv6 | TUN + signed privileged native service | Network Extension Packet Tunnel | Network Extension Packet Tunnel |
| Kill switch | OS Always-on + Block connections without VPN; verify OS state | Windows Filtering Platform persistent rules, privilege and crash recovery | Include-all/on-demand with documented OS exemptions | Network Extension routing/on-demand and platform exceptions |
| Only selected apps | VpnService.Builder.addAllowedApplication | Per-process routing/filters in audited service | Not a general consumer feature; managed per-app VPN requires MDM | Managed configuration or provider-specific restrictions, NOT generic arbitrary-app selection |
| Bypass selected apps | VpnService.Builder.addDisallowedApplication | Explicit and audited per-process bypass | Not for ordinary unmanaged iPhones | Only if managed/verified capabilities allow it |
| DNS / IPv6 leak prevention | Tunnel or block | Route and firewall enforcement | Native network settings; verify system exceptions | Native packet tunnel settings |

Android allowed and disallowed lists cannot be combined. In Android lockdown,
apps configured to bypass VPN may lose network access rather than use the
regular network. A UI must warn about this before applying rules.

Apple include-all routing still excludes certain network-control and cellular
system traffic, so do not promise literally all device packets are tunneled.
iOS Per-App VPN requires eligible managed-device configuration (MDM).
Windows per-app targeting and kill switch require native processes with the
necessary privileges, not merely a Flutter button.

Official platform references:
- https://developer.android.com/develop/connectivity/vpn
- https://developer.android.com/reference/android/net/VpnService.Builder
- https://developer.apple.com/documentation/networkextension/routing-your-vpn-network-traffic
- https://developer.apple.com/documentation/networkextension/netunnelprovidermanager
- https://developer.apple.com/documentation/networkextension/nevpnprotocol/includeallnetworks
- https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/vpn/vpn-profile-options
- https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/vpn/vpn-auto-trigger-profile
- https://learn.microsoft.com/en-us/windows/win32/fwp/windows-filtering-platform-start-page

## What is implemented here

1. A versioned desired policy: full tunnel, VPN for selected apps, bypass
   selected apps, strict kill-switch request, protected DNS, IPv6 tunnel-or-block,
   LAN access, auto reconnect, auto connect and smart server selection.
2. UI in Persian and English with a transparent non-active protection status.
3. Non-secret preferences scoped by a SHA-256 hash of tenant + account.
   Subscription tokens, private keys and passwords are never stored here.
4. A native capability handshake named com.twinpanel.twinconnect/vpn,
   method getCapabilities, contractVersion 1.
5. Fail-closed connection policy validation: an unverified OS protection
   capability never counts as active. A missing plugin returns unavailable.
6. Unit/widget tests for policy validation, kill-switch enforcement rejection,
   app selection restrictions, and tenant/account isolation.

This is deliberately a settings/architecture PR, NOT a working VPN client.
The current Connect VPN button remains disabled until an engine is integrated.

## Native capability contract

The future native method getCapabilities must return:
- contractVersion = 1
- engineReady, fullTunnel, includeApps, excludeApps
- killSwitchEnforced (not merely requested)
- dnsGuard, ipv6Guard, localNetworkBypass
- autoConnect, autoReconnect, managedDevice

The Flutter bridge defaults all fields to false when not verified. Runtime
connection start/stop needs a separately reviewed, versioned API, short-lived
account-scoped authentication, rollback and event streams. No future engine may
claim success before real tunnel and network protections are established.

## 2027 release backlog and acceptance order

P0 Security / prerequisite for actual connection:
- Native IPv4+IPv6 full tunneling and DNS-leak prevention; protected control
  traffic, routing and transport guard on every supported OS.
- OS-enforced kill switch with crash, network-change, sleep, reboot and
  service-restart tests; no false "protected" indicator.
- Per-protocol capability validation rather than pretending every TwinPanel
  protocol works on all OSs. WireGuard, OpenVPN, Xray and other supported
  protocols need independent engine compatibility and security audits.
- Secure credential storage (Android Keystore, Apple Keychain, Windows native
  protection), token rotation, no secrets in ordinary local preferences/logs.
- Device/session limit enforcement by owning panel; tenant isolation,
  entitlement revalidation, and no VPN access on revoked/expired licensing.
- Signed binaries, verified server origin, secure panel client APIs and strict
  app privacy disclosures.

P1 Advanced routing / reliability:
- Android installed-app picker and verified allow/deny routing.
- Windows per-process selection through a privileged, crash-safe service.
- Native Apple routing/managed app detection; no false consumer feature.
- Real latency and uptime measurements, favorites, connection history,
  last-good server, auto fastest server, smart failover and reconnection.
- Trusted/untrusted Wi-Fi rules, captive portal recovery, on-demand and
  background behaviors where the OS permits.
- Secure DNS choices, IPv6 behavior, local-network bypass (explicit warning),
  diagnostics, redacted opt-in logs and real usage/connection telemetry.
- Battery/metered network and TCP/UDP transport options without bypass leaks.

P2 User experience / release management:
- Bilingual Persian RTL / English LTR, accessibility, dark/light themes.
- Tenant/brand-specific logo, Telegram, renewal, support, account notices,
  and subscription status; account/profile switching.
- Signed self-updates, Windows installers, Android APK/AAB, notarized macOS
  applications and Apple-signed iOS distribution.
- Managed enterprise per-app mode as a separate entitlement and experience.
- Optional advanced multihop routing only after reliability/security tests.
- Privacy-by-design (no default traffic logging) and audit for marketplace
  rules and regional licensing requirements.

## Mandatory security test matrix before enabling Connect

- Kill switch requested but native lockdown missing -> prohibit connection.
- VPN drops, app crashes or Wi-Fi switches -> no non-VPN packet leakage under
  OS-supported strict mode.
- IPv6 unavailable in tunnel -> block IPv6; never quietly route it directly.
- DNS request fails to tunnel -> block; never fall back to unsecured DNS.
- Android include-only / exclude-only apps -> inspect actual app network egress.
- Windows process filters -> verify signed app identity, PID churn, crash
  recovery and safe cleanup on uninstall.
- iOS unmanaged -> app selector must not promise unavailable per-app routing.
- Managed iOS/macOS -> only enable after native OS profile verification.
- Changing customer/representative -> never reuse one account's policy or key.
- Panel license expired/revoked -> no new secure VPN sessions.
- Panel updates -> existing nodes, SNI, accounts, quotas and subscriptions
  remain unmodified.

The current Pull Request only adds the safe foundation and desired controls;
actual native engines and security tests are release blockers.
