# Legacy Exact Feature Matrix

> Source of truth: the production frontend exported from
> `/opt/twinpanel-web/candidates/ui-unified-20261003-094726`.
>
> This document is **not** a wish list. Every capability below is present in the
> exported legacy runtime or its API client. The `rebuild/legacy-exact-v1`
> branch must not mark a page complete until these flows are present in the new
> UI and connected to the same backend contract.

## Source fingerprint

- Uploaded archive SHA256: `905565247d39e8cbb49e417e6bc373800f51169affee0b8d626c76778ddc51be`
- Export manifest: `SOURCE_MANIFEST.sha256`
- Export manifest entries: 842
- Active import graph: 125 source files
- Main admin runtime: `app/twinpanel-control.tsx`
- Main API client: `app/twinpanel-api.ts`
- Customer runtime: `app/real-customer-panel.tsx`
- Reseller runtime: `app/reseller/page.tsx`
- Reseller bot runtime: `app/reseller/reseller-bot-panel.tsx`

## Completion rule

A page is only complete when all legacy data, actions, dialogs, filters,
confirmation steps, status displays and cross-navigation flows are available.
Visual layout may be modernized, but feature placement must remain discoverable
in the same workflow. Raw JSON is not a replacement for a legacy detail view.

## Admin parity

| Legacy section | Legacy component | Required capability set | Backend/API contracts observed |
| --- | --- | --- | --- |
| Dashboard | `Command` | live business/system summary, subscription/tunnel/node health, payment summary, protocol status, individual protocol restart, restart-all confirmation, history/status panels | `adminPaymentIntents`, `coreProtocols`, `dashboardSummary`, `nodes`, `restartAllCoreProtocols`, `restartCoreProtocol`, `stats`, `subscriptions`, `systemHealth`, `tunnels` |
| Live network | `NetworkCenter` | node/tunnel topology, live path status, selected node/path details, refresh state | `nodes`, `tunnels` |
| Servers / Nodes | `Nodes` | node list/filter/detail, SSH access view/edit, node domains, protocol health, per-protocol restart, repair protocols, agent upgrade, maintenance toggle, tunnel-fabric install/status, node deletion, add-node provisioning entry | `deleteNode`, `installTunnelFabric`, `nodeAccess`, `nodeDomains`, `nodes`, `protocolHealth`, `repairProtocolsSaved`, `restartProtocol`, `saveNodeAccess`, `toggleMaintenance`, `updateNodeDomain`, `upgradeAgent` |
| Tunnels / Failover | `TunnelCenter` | create/register tunnel, Iran→Exit selection, transport mode Auto/Manual, SSH tunnel install, MTunnel install/repair/health, Backhaul install/status, prepare, health, enable/disable, edit, delete, transport priority/status | `deleteTunnel`, `installBackhaul`, `installMtunnel`, `installSshTunnel`, `mtunnelHealth`, `nodes`, `prepareTunnel`, `registerTunnel`, `repairMtunnel`, `setTunnelTransportMode`, `toggleTunnel`, `tunnelHealth`, `tunnelTransports`, `tunnels`, `updateTunnel` |
| Users | `UsersCenter` | pagination/search/status filters, create/edit user, activate/deactivate, reset password, delete user, user detail, subscriptions-by-user, inline subscription management including plan/nodes/protocols/account credential editing, extend traffic/days, delete subscription | `createAdminUser`, `deleteSubscription`, `deleteUser`, `editSubscription`, `extendSubscription`, `nodes`, `plans`, `resetUserPassword`, `subscriptionsByUser`, `toggleUser`, `updateUser`, `usersPage` |
| Security | `SecurityCenter` | security overview, risk/status filtering/search, subscription suspend/reactivate from security flow | `securityOverview`, `setSubscriptionActive` |
| Plans | `PlansCenter` | list/filter/search, create/edit/delete, description, duration, traffic, price, device limit, protocol availability, publish/active state | `createPlan`, `deletePlan`, `plans`, `updatePlan` |
| Subscriptions | `SubscriptionsCenter` | list/search/filter, customer/plan/account username, traffic/expiry/status, create subscription, edit plan/traffic/nodes/protocols/account username/password, manual extension, suspend/activate, provision account, delete, connection-info detail, subscription link/QR flow | `deleteSubscription`, `editSubscription`, `extendSubscription`, `nodes`, `plans`, `provisionSubscriptionAccount`, `setSubscriptionActive`, `subscriptionConnectionInfo`, `subscriptions`, `users` |
| Payments | `AdminPaymentsPanel` | list/filter, receipt loading/preview, approve/reject with reason/status feedback | `adminPaymentIntents`, `approvePayment`, `rejectPayment` |
| Wallets | `AdminWalletsPanel` | customer balances, top-up requests, approve/reject top-up, manual balance adjustment with note | `adjustCustomerWallet`, `adminWalletTopups`, `adminWallets`, `approveWalletTopup`, `rejectWalletTopup` |
| Store / website | `WebsiteHub` + `AdminStorefrontSettingsPanel` + footer editor | content tab, layout/section ordering/visibility, SEO, storefront settings, footer editor, plan navigation | `storefrontSettings`, `updateStorefrontSettings` |
| Resellers admin | `Resellers` | stats, list/search, create/edit/enable/disable/delete reseller, reseller plan assignment/pricing, traffic balance adjustment, traffic package create/edit/delete | `adjustResellerTraffic`, `createReseller`, `createResellerTrafficPackage`, `deleteReseller`, `resellerPlans`, `resellerStats`, `resellerTrafficBalance`, `resellerTrafficPackages`, `resellers`, `setResellerPlan`, `toggleReseller`, `updateReseller`, `updateResellerTrafficPackage` |
| Telegram bot | `TelegramHub` | token save, test, install, start, stop, restart, status and logs | `telegramBotInstall`, `telegramBotLogs`, `telegramBotRestart`, `telegramBotSaveToken`, `telegramBotStart`, `telegramBotStatus`, `telegramBotStop`, `telegramBotTest` |
| Support | `AdminSupportPanel` | ticket list/search/filter, detail/messages, reply, image attachment/preview, ticket actions/status transitions | `/v1/admin/support/tickets*` |
| Backups | `AdminBackupPanel` | backup list/create/download/upload/restore/delete, recovery key, schedule settings (hourly/daily/weekly, timezone, retention), Telegram delivery verification/test | `/v1/admin/backups*` |
| Discounts | `AdminDiscountsPanel` | discount list/create/update/disable, code/value/limits/status | `mainCreateDiscount`, `mainDisableDiscount`, `mainDiscounts` |
| Settings | `Settings` | admin profile/email, password change, 2FA status/setup/enable/disable, L2TP central PSK load/generate/update/show-hide, Mother access global + reseller overrides, notification settings, SMS Reader, commerce/payment settings | `changePassword`, `customerUpdateEmail`, `generateL2tpPsk`, `motherAccessSettings`, `resellers`, `twoFactorDisable`, `twoFactorEnable`, `twoFactorSetup`, `twoFactorStatus`, `updateL2tpPsk` |
| Domains / SSL | `DomainsCenter` | list/create/edit/delete domain, domain type/status, SSL request/issue state | `createDomain`, `deleteDomain`, `domains`, `sslDomain`, `updateDomain` |

## Shared node provisioning flow

The add-node modal in the legacy control is a required flow, not a generic node
form.

- SSH connection test before install.
- Iran node: database registration + SSH access only; no user VPN protocols are installed.
- Exit node: full provisioning with protocol selection.
- Protocol choices: Cisco, OpenVPN, WireGuard, L2TP, V2Ray/Xray.
- Country code, SSH host/port/user/password.
- Progress/status/error feedback.
- Partial Iran registration is rolled back if SSH access saving fails.

## Subscription detail parity

This is a hard requirement because it was the first visible parity failure.

The new subscription workflow must expose, in the subscription context:

- user/customer identity
- plan
- account username and password
- total traffic / used traffic
- start and expiry
- selected/available protocols
- assigned/global node context used by the backend
- activate/suspend
- extend traffic
- extend duration
- edit subscription
- edit account username/password
- provision/re-provision
- delete
- connection information
- public subscription link
- QR code
- per-protocol server/port/transport details
- OpenVPN config/download
- WireGuard config/download/QR
- L2TP username/password/PSK/server
- Cisco/OpenConnect credentials/server
- V2Ray/Xray URI/QR
- copy/open/download actions

A raw `JSON.stringify(connectionInfo)` panel does **not** satisfy parity.

## User-detail parity

Selecting/managing a user must keep the legacy nested workflow:

- identity and membership information
- active/inactive status
- edit user
- reset password
- toggle active
- all subscriptions belonging to that user
- subscription actions available without leaving user management
- destructive user deletion with dependent-subscription awareness

## Customer portal parity

Source: `app/real-customer-panel.tsx`.

Observed live contracts:

`changePassword`, `createStoreOrder`, `customerUpdateEmail`, `me`, `myPaymentIntents`, `myStoreOrders`, `mySubscriptions`, `publicPlans`

Required flows:

- authenticated customer profile
- active/history subscription filtering
- subscription traffic/expiry/status
- connection information
- plan browsing and purchase/order creation
- order history
- payment intent/history
- email/profile update with verification/password flow
- password change
- customer notifications
- support/chat access

## Reseller portal parity

Source: `app/reseller/page.tsx`.

Observed contracts:

`login`, `resellerBuyTraffic`, `resellerChangePassword`, `resellerConnectionInfo`, `resellerCreateCustomer`, `resellerCreateDiscount`, `resellerCustomersPortal`, `resellerDashboard`, `resellerDeleteSubscription`, `resellerDisableDiscount`, `resellerDiscounts`, `resellerEditSubscription`, `resellerExtendSubscription`, `resellerMe`, `resellerSalesPlans`, `resellerSellSubscription`, `resellerSetSalesPlanPrice`, `resellerSubscriptionsPortal`, `resellerToggleSubscription`, `resellerTrafficPackagesPortal`, `resellerTrafficTransactionsPortal`, `resellerUpdateDiscount`, `resellerUpdateProfile`

Required flows:

- reseller authentication/profile
- dashboard/statistics
- customer list + create customer
- subscription list
- sell/create subscription
- edit subscription
- extend subscription
- activate/suspend
- delete subscription
- connection/subscription-link info
- traffic balance and package purchase
- traffic transaction history
- reseller discounts
- reseller plan selling-price controls
- profile update
- password change
- notification flow

## Reseller bot parity

Source: `app/reseller/reseller-bot-panel.tsx`.

Observed contracts:

`resellerBotActivate`, `resellerBotApproveOrder`, `resellerBotCreatePaymentMethod`, `resellerBotDeactivate`, `resellerBotDeletePaymentMethod`, `resellerBotOrders`, `resellerBotPaymentMethods`, `resellerBotRejectOrder`, `resellerBotSaveToken`, `resellerBotStatus`, `resellerBotTest`, `resellerBotUpdatePaymentMethod`, `resellerBotUpdateSettings`

Required flows:

- bot token/settings/status
- activate/deactivate/test
- welcome/support text
- payment methods CRUD
- order queue/detail
- receipt preview
- approve/reject orders

## Storefront parity

The storefront is backend-driven. It must preserve:

- public plan loading
- discount-code flow
- plan selection / checkout entry
- protocol section
- service/benefit section
- guides by OS and protocol
- account/customer-panel entry
- FAQ
- configurable section visibility/order
- dynamic storefront content/SEO/footer

## Notification / SMS parity

- Admin notification channel settings and Telegram test.
- Send user notification to all or one user.
- notification kind, title, message, Telegram flag and send history/read counts.
- SMS Reader settings, device/import code, matching/verification controls.
- Automagen device creation flow.

## Migration policy

1. Do not merge `rebuild/legacy-exact-v1` into `main` until this matrix is checked.
2. Do not remove a legacy action because a newer screen has a different layout.
3. Do not replace a structured legacy flow with a raw JSON viewer.
4. Do not expose `.env`, credentials, certificates, private keys or production backups.
5. Modernization is visual/UX only; business capability parity is mandatory.
