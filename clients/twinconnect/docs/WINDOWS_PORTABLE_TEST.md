# TwinConnect Windows x64 — Portable Preview

This is a **UI test build, not an active Windows VPN client**. It is made for quick manual testing on Windows 10/11 x64 without requiring Flutter, Android Studio or a server.

## Download

Open the Windows Portable Preview GitHub Actions run from this branch/PR. Under **Artifacts**, download **TwinConnect-Windows-x64-Portable**. Extract the archive (and if needed the inner TwinConnect-Windows-Preview.zip) completely, then run twinconnect.exe while keeping its DLL/data directory beside it. The executable is unsigned, so Windows SmartScreen might show a publisher warning; only run trusted builds from this repo.

## Test plan

1. Launch `twinconnect.exe` with no existing subscription configured.
2. Click **Explore Windows demo** / **مشاهده نسخه آزمایشی ویندوز**.
3. Confirm a prominent **OFFLINE DEMO** banner is visible and the brand shows `TwinConnect Demo`.
4. Check all 16 protocols and that no protocol is falsely shown as a working VPN engine.
5. Switch English and فارسی and inspect both text directions.
6. Open **Advanced VPN settings** via the top settings icon and test full-tunnel, Kill Switch, DNS/IPv6 and per-app settings. They save local desired preferences but **never alter Windows networking** in this build.
7. The Windows Connect action is disabled. It must not show a fake connected state.
8. The live panel login still depends on deployment of the *separate* vendor/panel registration PRs and a configured vendor directory URL.

## Real VPN testing still needed

For actual end-to-end WireGuard and Cisco/OpenConnect **on Windows**, next steps are:

- Build an audited Windows native tunnel/process manager: WireGuard for Windows/Wintun or official supported integration, and an independent OpenConnect-based engine.
- Require explicit admin permission for network driver installation, route changes, and WFP Kill Switch rules.
- Validate full-tunnel IPv4 and IPv6 routes, DNS no-leak policy, and OS privileges.
- Reuse the existing TwinPanel profile API after authorized account login (do not rewrite credentials or node addresses).
- Only report `connected` once the actual native engine and handshake/traffic tests confirm connectivity.
- Test clean disconnect, crash recovery and uninstall without orphaned network filters.
- Sign binaries before a broad customer rollout.

**Security:** no user profile, license key, VPN private key or subscription token is bundled in the Windows preview. The demonstration is fictional and offline.

## Build status

`.github/workflows/twinconnect-windows-preview.yml` creates, analyzes, tests, compiles and ZIPs the standalone Windows x64 preview automatically on branch updates or PRs. Always check the green build and Artifact panel before claiming a downloadable ZIP exists.
