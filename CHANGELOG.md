# TwinPanel Changelog

## 1.1.0-rc.655 — 2026-11-07

### V2Ray/Xray late-loading node actions
- Observe asynchronous V2Ray server group insertion and attach a real copy-all-existing-configs action to every newly rendered server. Avoid duplicate buttons and mutation feedback loops.
- Preserve the rc.654 V2Ray cards, mobile/desktop Connection layout and protocol-specific download/import behavior.
- The public feed intentionally includes only eligible stored profiles; missing runtime/configuration inbounds are **not** fabricated by this UI update.
- No database schema, node listener or tunnel configuration changes.

## 1.1.0-rc.654 — 2026-11-07

### V2Ray/Xray Connection repair
- Add an explicit **Copy server configs** button to every V2Ray/Xray node; copies all distinct, actually available VLESS URIs for that node.
- Remove conflicting fixed-height/overflow presentation restrictions from expandable Xray profile cards, preserving all returned profile rows and their per-profile copy/import buttons.
- Keep Windows four-action footer and Android one-primary-plus-three layout, client download links and configured TwinPanel theme.
- **Data diagnostic:** the tested account's V2Ray metadata currently provides 1, 1, 1 and 2 configurations for its four nodes; this frontend fix does not provision missing inbounds or pretend the nodes have three live configurations each. Provisioning requires separate runtime/back-end verification.
- No intentional changes to VPN protocol configuration, credentials, tunnels or node runtime.

## 1.1.0-rc.653 — 2026-11-07

### Official package parity
- Rebuild the installable release from the latest GitHub source rather than reusing the older rc.652 artifact. This includes the Connection changes that had previously been applied only as production hotfixes.
- Windows: four available Connection footer actions in one horizontal row; preserve the actual client-download action and the original copy/link/import handlers.
- Android: when four actions are available, one full-width primary action above three equal actions. No placeholder controls if an action does not exist for a protocol.
- OpenVPN, WireGuard, AmneziaWG: preserve genuine config-file download and multi-server ZIP routes. Other protocols retain their original compatible-app import actions.
- Restore the supported protocol-specific client install links (including Karing, Sudoku, TrustTunnel, OpenConnect) with device-aware choices.
- Retain unified theme colors, server row layouts, and the mobile server-detail modal.
- No changes intended to VPN runtime, database, node tunnels, or credentials.

### Validation and limits
- Official prebuilt release workflow is responsible for building and hashing the candidate artifact before stable manifest publication.
- Complete interactive visual regression across all supported devices and protocols has not been verified.

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

