# TwinPanel Changelog

## 1.1.0-rc.652 — 2026-11-07

### Connection — user interface and client delivery
- Unified desktop/mobile Connection colors with configured TwinPanel brand palette, including background, header, protocol cards, server rows, footer actions and detail dialog.
- Moved the single device-specific **Download app** action into the existing bottom action bar; removed repeated standalone client-download cards.
- Added client download access for AmneziaWG and TrustTunnel, and removed the unnecessary L2TP/IPsec app-download action.
- Improved OpenVPN/WireGuard/AmneziaWG per-server file download/copy actions while retaining existing config links and credentials.
- Normalized mobile protocol grid to show each name beneath its icon.
- Aligned native and modern server rows and made mobile copy/add buttons readable without overlap.
- Added mobile server-detail modal behavior while keeping original configuration/copy controls.
- Removed unnecessary recurring footer DOM reconciliation.

### Release scope and validation
- UI-only Connection modifications; no intentional changes to VPN runtime, database, credentials, nodes, or tunnels.
- Python/JavaScript syntax, production Connection HTTP 200 and API health HTTP 200 were verified during hotfix deployment.
- **Visual mobile browser automation for all protocols has not been completed.** Publishing and install/update checks are handled by the prebuilt release workflow.

