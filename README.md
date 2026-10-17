# TwinPanel

<p align="center">
  <strong>English</strong> · <a href="README_FA.md">فارسی</a>
</p>

# TwinPanel — Self-Hosted VPN Control Plane

TwinPanel is a complete self-hosted control plane for operating a VPN service: users, subscriptions, VPN protocols, Iran/Exit nodes, tunnels, transport failover, storefront, payments, wallets, resellers, Telegram, support, backups, releases, and licensing.

The platform is designed so the core operational stack runs on infrastructure you control while day-to-day service management is handled from one unified panel.

> **English is the default repository language.** Click **فارسی** above to open the full Persian RTL version.

---

## Table of contents

- [Overview](#overview)
- [Core capabilities](#core-capabilities)
- [Users and subscriptions](#users-and-subscriptions)
- [VPN protocols](#vpn-protocols)
- [Modern Xray / V2Ray](#modern-xray--v2ray)
- [Nodes, tunnels, and failover](#nodes-tunnels-and-failover)
- [Storefront and payments](#storefront-and-payments)
- [Wallet](#wallet)
- [Reseller platform](#reseller-platform)
- [Telegram](#telegram)
- [Account delivery and connection pages](#account-delivery-and-connection-pages)
- [Support and notifications](#support-and-notifications)
- [Domains, SSL, and branding](#domains-ssl-and-branding)
- [Backup, security, and diagnostics](#backup-security-and-diagnostics)
- [Updates and rollback](#updates-and-rollback)
- [Trial and licensing](#trial-and-licensing)
- [User interface](#user-interface)
- [Architecture](#architecture)
- [Quick install](#quick-install)
- [Requirements](#requirements)
- [Important paths](#important-paths)
- [Security rules](#security-rules)

---

## Overview

TwinPanel is built for operators who want the Backend, Frontend, database, Redis, Nginx, systemd services, provisioning logic, and operational tooling to run on their own server while configuration and daily operations remain accessible from a unified web interface.

The product includes:

- Central administration panel
- Customer panel
- Reseller panel
- Storefront and subscription checkout
- Payment and receipt management
- Customer and reseller wallet flows
- Telegram sales and management flows
- Iran and Exit node management
- Tunnel and transport management
- Node provisioning, repair, and recovery
- VPN account delivery and public connection pages
- Support and notification centers
- Backup and restore tooling
- License, release, update, and rollback workflow
- Persian RTL and English LTR
- Dark and Light themes

---

## Core capabilities

| Area | Capabilities |
|---|---|
| Users | User lifecycle, status, role-aware access, administrative isolation |
| Subscriptions | Create, edit, renew, suspend, remove, expiration, volume, delivery |
| VPN protocols | Cisco/OpenConnect, OpenVPN, WireGuard, L2TP/IPsec, V2Ray/Xray |
| Nodes | Iran and Exit nodes, provisioning, health, recovery, protocol configuration |
| Tunnels | Iran → Exit paths, health, latency, watchdog, failover, multi-transport runtime |
| Modern Xray | XHTTP/REALITY, gRPC/REALITY, WebSocket/TLS, HTTPUpgrade/TLS |
| Store | Plans, storefront configuration, checkout, discounts, orders |
| Payments | Card/receipt flow, USDT-BEP20, TRX, BNB, market rates, receipt review |
| SMS Reader | Bank-message matching for plan purchases or wallet top-ups |
| Wallet | Balance, top-up, approval/rejection, admin adjustment, notifications |
| Resellers | Traffic credit, owned plans, pricing, customer sales, reseller notifications |
| Telegram | Sales, orders, payment flows, reseller commerce, wallet top-ups, broadcasts |
| Support | Customer support routes, admin responses, notification centers |
| Domains & SSL | Domain and TLS management from the product runtime |
| Branding | Configurable product/brand presentation |
| Backup | Backup/restore integration and pre-update backup workflow |
| Release | Version display, guarded update, health verification, rollback |
| Licensing | Seven-day trial and paid activation integration without reinstalling the product |

---

## Users and subscriptions

TwinPanel covers the complete user and subscription lifecycle:

- Create and manage users
- Create subscriptions
- Edit subscription settings
- Renew subscriptions
- Suspend and reactivate subscriptions
- Remove subscriptions
- Manage expiration dates
- Manage traffic volume and usage
- Assign one or more protocols
- Assign connection nodes/routes
- Generate per-protocol credentials
- Deliver connection information in the customer panel
- Generate controlled public connection links
- Enforce subscription state and quota rules
- Record usage events for quota and reseller traffic accounting

The goal is to keep commercial state, access credentials, connection delivery, and network enforcement connected to the same subscription record.

---

## VPN protocols

TwinPanel supports multiple protocol families so an operator is not forced to depend on one connection method.

### Cisco / OpenConnect

- Credential creation and management
- Endpoint and port delivery
- Customer connection information
- Direct or tunnel-backed access paths

### OpenVPN

- Credential and client identity management
- Client configuration delivery
- Central PKI compatibility in the current runtime
- Client use across Windows, macOS, Android, iOS, and Linux

### WireGuard

- WireGuard profile generation and delivery
- QR/config-oriented customer delivery
- Endpoint routing through a node or managed tunnel path

### L2TP/IPsec

- L2TP connection information
- PSK handling in the infrastructure layer
- Customer credential delivery

### V2Ray / Xray

- VLESS/Xray credential management
- Compatibility support for legacy profiles
- Separate modern profiles for newly provisioned connections

---

## Modern Xray / V2Ray

The modern Xray runtime exposes multiple independent VLESS profiles:

- **VLESS XHTTP + REALITY**
- **VLESS gRPC + REALITY**
- **VLESS WebSocket + TLS**
- **VLESS HTTPUpgrade + TLS**

The legacy plain profile can remain available for compatibility, while newly provisioned credentials can use separate modern listeners.

When a valid Exit domain and certificate are available, TLS-based profiles can use that domain. REALITY-based profiles provide a separate modern path that does not require the same TLS-domain model.

This lets operators keep compatibility with existing users while moving new accounts toward newer transport profiles.

---

## Nodes, tunnels, and failover

### Node management

TwinPanel distinguishes between **Iran** and **Exit** nodes.

Node operations include:

- Store and manage node connection data
- Show operational status
- Provision services from the panel
- Repair and recover nodes
- Manage per-node protocol configuration
- Run operational health and diagnostics
- Use node information for account delivery and tunnel routing

### Tunnel management

Tunnel management is designed to keep the VPN service layer separate from the Iran → Exit transport layer.

Capabilities include:

- Create Iran-to-Exit tunnel paths
- Track active transport
- Online / Offline / Degraded status
- Latency tracking
- Last-error visibility
- Background tunnel watchdog
- Managed tunnel orchestration
- Install/remove supported transport runtimes
- Failover across supported transports
- Canary-first validation for modern transport candidates
- Preserve compatibility paths during migrations

Because the transport layer is separated from the customer VPN account layer, changing a tunnel transport does not necessarily require recreating every customer account.

---

## Storefront and payments

TwinPanel includes a storefront and commerce layer for selling subscriptions directly.

### Storefront

- Plan listing
- Subscription purchase flow
- Storefront configuration
- Storefront content/settings management
- Discounts
- Checkout
- Order/payment status

### Payment methods

The current runtime contains payment paths for:

- Card-to-card / manual receipt review
- **USDT on BEP20**
- Native **TRX**
- Native **BNB**

### Market-rate handling

- Live/resilient crypto market-rate flow
- Payment quote generation
- Immutable quote behavior for created payment intents
- Operational payment runtime status

### Receipt workflow

- Receipt submission
- Admin receipt review
- Local receipt handling
- Telegram-related receipt compatibility
- Payment result notifications

---

## SMS Reader

The SMS Reader runtime is designed to automate bank-payment matching.

Capabilities include:

- Receive bank SMS events
- Operational SMS Reader dashboard
- Attempt payment matching
- Match subscription purchases
- Match wallet top-ups
- Prevent the same bank event from being consumed by both a plan payment and a wallet top-up

This allows manual banking workflows to be automated without losing an auditable approval path.

---

## Wallet

The wallet system includes both customer and administrator operations:

- Display wallet balance
- Request wallet top-up
- Attach a payment flow to a top-up
- Admin approve/reject workflow
- Credit balance after a valid approval
- Manual administrative balance adjustment
- Wallet-related event history
- Wallet notifications
- Integration with SMS Reader and Telegram flows where applicable

---

## Reseller platform

TwinPanel includes a separate reseller layer rather than treating every seller as a normal administrator.

Reseller capabilities include:

- Create and manage resellers
- Reseller profile management
- Dedicated reseller portal
- Sell subscriptions to reseller customers
- Manage reseller customers and subscriptions
- Traffic credit / volume credit
- Traffic purchase flows
- Shared traffic pools
- Reseller-owned plans
- Reseller pricing and product controls
- Subscription renewal and volume changes
- Reseller notifications
- Telegram reseller order/payment flows

In the newer traffic model, accepted real usage events can drive traffic-pool deduction, so simply creating an account does not have to equal traffic consumption.

---

## Telegram

Telegram is integrated as an additional commerce and management surface on top of the same Backend.

Supported flows include:

- Connect a Telegram bot to TwinPanel
- Subscription sales
- Order management
- Payment flow integration
- Receipt submission/handling
- Reseller ordering
- Reseller wallet top-ups
- Notifications
- Administrative broadcast flows where enabled

Telegram does not replace the main database or administration panel; it works against the same Backend so web and bot operations stay synchronized.

---

## Account delivery and connection pages

TwinPanel can deliver a subscription through a controlled public connection page.

Capabilities include:

- Persistent share code / share token
- Public connection page
- Active/inactive/expired-state handling
- QR generation on supported routes
- Credential and connection-info delivery
- Client download references by operating system
- Windows
- macOS
- Android
- iOS
- Linux

Runtime client references include tools such as OpenVPN Connect, WireGuard, Cisco Secure Client, v2rayN, and Hiddify, depending on platform and protocol.

This lets a customer receive the connection material they need without exposing administrative APIs.

---

## Support and notifications

TwinPanel includes separate customer, admin, and reseller communication paths:

- Customer support system
- Administrative support responses
- User Notification Center
- Admin Notification Center
- Reseller notifications
- Operational event notifications
- Background notification watch loop

---

## Domains, SSL, and branding

### Domains and TLS

- A first installation can start without requiring a domain
- A domain can be configured later
- Domain and TLS settings are managed through product routes
- Valid Exit domains/certificates can be used by TLS-based Xray profiles

### Branding

- Configurable product/brand presentation
- Branding settings managed by the product
- UI areas can consume configurable branding instead of relying on a permanently hard-coded display name

---

## Backup, security, and diagnostics

### Backup

- Administrative backup routes
- Pre-upgrade backup workflow
- Restore workflow through the product's operational tooling
- Dedicated backup storage path

### Security

- Authentication and role checks
- Admin-only routes for privileged operations
- 2FA runtime support
- License mutation guard
- Quota/security routes
- Administrative user/reseller isolation logic
- Locally generated installation secrets with restricted permissions

### Health and diagnostics

TwinPanel exposes operational health checks for both the service and its dependencies:

- `/health`
- `/health/ready`
- Database readiness check
- Redis readiness check
- Post-update health verification
- Runtime status for operational modules

---

## Updates and rollback

TwinPanel is designed around guarded releases instead of manually replacing production files.

A normal public update path includes:

1. Detect the currently installed version
2. Resolve the published Stable manifest
3. Create a pre-upgrade backup
4. Fetch the exact public Git commit declared by the manifest
5. Verify the checked-out commit and release `VERSION`
6. Install/build the new release
7. Atomically switch `/opt/twinpanel/current`
8. Restart services
9. Run health verification
10. Automatically roll back if the new release fails health verification

The installed version is surfaced inside the panel and customer updates come only from the validated public Stable manifest.

---

## Trial and licensing

TwinPanel retains integration for seven-day trials and paid licenses. The current public `1.1.0-rc.1` manifest is installable without mandatory license enforcement (`license_required: false`) so clean public installation can be validated independently of a future vendor license service.

The licensing architecture is designed so it can later support:

- Trial state bound to installation identity
- Paid activation without deleting users, subscriptions, nodes, tunnels, or the database
- Signed entitlement validation
- Bounded offline grace for temporary license-service connectivity failures
- Keeping admin login, activation, backup/export, and diagnostics accessible according to license policy

More details:

- [`LICENSE_TRIAL_SPEC.md`](LICENSE_TRIAL_SPEC.md)
- [`PRODUCT_DISTRIBUTION.md`](PRODUCT_DISTRIBUTION.md)

---

## User interface

TwinPanel uses a shared product design language across its surfaces:

- **English LTR**
- **Persian RTL**
- Dark mode
- Light mode
- Admin panel
- Customer panel
- Reseller panel
- Storefront
- Public account-delivery pages
- Responsive layouts for desktop and mobile use

---

## Architecture

```text
Internet
   |
 Nginx :80 / :443
   |----------------------> Next.js Web :3000
   |                           |
   |                           +--> same-origin /v1/*
   |
   +------------------------> FastAPI :8095
                                |
                      +---------+---------+
                      |                   |
                PostgreSQL :5432      Redis :6379
                      |
                      +--> Users / Subscriptions / Store / Payments
                      +--> Resellers / Wallet / Notifications / Runtime state

FastAPI
   |
   +--> Node provisioning / recovery
   +--> Tunnel management / watchdog / transports
   +--> VPN protocol credentials
   +--> Modern Xray profiles
   +--> Telegram / SMS Reader / support
   +--> Backup / release / license
```

Frontend and API services run locally, while Nginx publishes the public HTTP/HTTPS endpoint.

---

## Quick install

Customer installations use the public installer in this repository:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/twinpanel/main/install.sh | sudo bash
```

No GitHub account, SSH key, Deploy Key, Personal Access Token, manual clone, branch selection, or commit selection is required from the customer. The installer resolves `releases/stable.json` and fetches the exact validated public Git commit declared by that manifest.

Full English installation guide:

[`docs/INSTALL_EN.md`](docs/INSTALL_EN.md)

Persian installation guide:

[`docs/INSTALL_FA.md`](docs/INSTALL_FA.md)

---

## Requirements

Current official installation requirements:

- Clean Ubuntu 22.04 or Ubuntu 24.04 server
- Root access
- 2 GB RAM recommended minimum
- 2 vCPU recommended minimum
- At least 20 GB free disk space
- Outbound Internet access for installation/update downloads
- Ports 80 and 443 for the public web endpoint

The installer prepares the required runtime stack, including PostgreSQL, Redis, Python, Node.js, Nginx, and systemd services.

---

## Installation flow

The official public installer performs the installation as a guarded sequence:

1. Validate Ubuntu and root access
2. Resolve the published Stable manifest
3. Read the release version and exact public source commit
4. Fetch that commit over HTTPS
5. Verify the checked-out Git SHA and `VERSION`
6. Install dependencies and runtime services
7. Install Backend and Frontend
8. Generate local secrets
9. Initialize the database
10. Bootstrap the first administrator
11. Install systemd services
12. Install the `twinpanel` / `tp` SSH management command
13. Configure/enable Nginx
14. Run final health checks

The generated initial administrator password is stored in the root-only file:

```text
/root/twinpanel-initial-admin.txt
```

After first login, change the administrator credentials and remove the file. Reinstall/update preserves an existing administrator instead of silently changing its credentials.

---

## Important paths

```text
/opt/twinpanel/current                 active release
/opt/twinpanel/releases                installed releases
/opt/twinpanel/venv                    Python virtual environment
/etc/twinpanel/backend.env             Backend runtime environment
/etc/twinpanel/frontend.env            Frontend runtime environment
/etc/twinpanel/install.env             install/release settings
/var/lib/twinpanel-backups             backups
/var/lib/twinpanel-license             release/license/update state
/root/twinpanel-initial-admin.txt      initial admin credentials
/usr/local/bin/twinpanel               SSH management command
/usr/local/bin/tp                      short SSH management alias
```

---

## Release source of truth

The repository default and canonical project branch is:

```text
main
```

Customer-installable releases are selected through [`releases/stable.json`](releases/stable.json), which pins the public installation to an exact validated source commit. Experimental branches such as `feat/*`, `fix/*`, `preview/*`, or local production branches are not direct customer installation sources.

The product version is stored in:

[`VERSION`](VERSION)

---

## Security rules

Never commit the following to GitHub:

- Production secrets
- License signing keys
- Telegram bot tokens
- SSH private keys
- Certificate private keys
- Production `.env` files
- Database dumps
- Confidential customer data

In the production architecture, Web/API services can remain on loopback while Nginx publishes the public endpoints.

---

## More documentation

- [English installation guide](docs/INSTALL_EN.md)
- [English product overview](docs/PRODUCT_EN.md)
- [Persian installation guide](docs/INSTALL_FA.md)
- [Persian product overview](docs/PRODUCT_FA.md)
- [Trial and license specification](LICENSE_TRIAL_SPEC.md)
- [Product distribution model](PRODUCT_DISTRIBUTION.md)

---

**TwinPanel** — one control plane for VPN infrastructure, customers, commerce, and operations.
