# TwinPanel 2027 — Legacy Feature Parity Matrix

This file is the migration contract. A feature is not considered migrated just because a menu item exists. `DONE` means the 2027 UI calls the real legacy-compatible backend endpoint and does not show sample business data. `PARTIAL` means the live contract is used but one or more legacy operations are intentionally still missing from the new UI.

## Rules

- Preserve the 2027 visual system; do not replace live features with simplified placeholder UI.
- Never ship fake users, servers, balances, orders, domains, bot names, backup files, revenue, health states or traffic values.
- Reuse the proven backend contracts and database; do not invent a parallel schema.
- Public store remains public. Customer/Admin/Reseller operations remain role protected.
- Production domains come from Domains & SSL; no customer domain is hard-coded.
- Secrets, private keys, backups and offline application binaries are never committed to Git.
- A backend endpoint by itself is not enough for `DONE`; the active 2027 route must expose the operation.

## Authentication / identity

| Capability | Legacy contract | 2027 status |
|---|---|---|
| Login | `POST /v1/auth/login` | DONE |
| Registration (customer only) | `POST /v1/auth/register` | DONE |
| Current user | `GET /v1/auth/me` | DONE |
| Change email/password | `/v1/auth/me/email`, `/v1/auth/change-password` | DONE |
| 2FA | `/v1/auth/2fa/*` | DONE |
| Admin guard | user role `admin` | DONE |
| Reseller detection | `GET /v1/reseller/me` | DONE |
| Stable customer session | `/v1/auth/me` authoritative; reseller probe non-destructive | DONE |
| Login return path | safe internal `next=` return | DONE |

## Admin dashboard / system

| Capability | Contract | Status |
|---|---|---|
| Dashboard stats | `/v1/admin/stats`, `/v1/admin/dashboard-summary` | DONE |
| Revenue chart | real admin payment intents | DONE |
| Subscription donut | real subscriptions | DONE |
| Nodes/tunnels widgets | `/v1/nodes`, `/v1/tunnels` | DONE |
| Protocol health | `/v1/admin/core-protocols` | DONE |
| Restart one/all core protocols | `/v1/admin/core-protocols/{protocol}/restart`, `/restart-all` | DONE |
| System health | `/v1/admin/system-health` | DONE |
| Security overview | `/v1/admin/security/overview` | DONE |

## Users / subscriptions / plans

| Capability | Contract | Status |
|---|---|---|
| Users list/create/edit/delete | `/v1/admin/users*` | DONE |
| Toggle/reset password | admin user routes | DONE |
| Subscriptions list | `/v1/subscriptions` | DONE |
| Create/activate/suspend/delete | subscription admin routes | DONE |
| Admin edit | `/v1/subscriptions/{id}/admin-edit` | DONE |
| Extend/manual limits | `/extend`, `/manual-limits` | DONE |
| Provision account | `/provision-account` | DONE |
| Refresh credentials | `/refresh-simple-passwords` | DONE |
| Connection information | `/connection-info` | DONE |
| Plans list | `/v1/plans/admin/all` | DONE |
| Plans CRUD | `/v1/plans*` | DONE |

## Nodes / tunnels / provisioning

| Capability | Contract | Status |
|---|---|---|
| Nodes list | `/v1/nodes` | DONE |
| Node creation | `/v1/provision/install` | DONE through Provisioning |
| Node maintenance | `/v1/nodes/{id}/maintenance` | DONE |
| Node health/protocols | node health routes | DONE |
| Node edit/delete lifecycle | node routes | PARTIAL — lifecycle API exists; full inline editor is not yet exposed |
| Tunnels list/create/delete/toggle/prepare/health | `/v1/tunnels*` | DONE core |
| Generic tunnel PATCH editor | `PATCH /v1/tunnels/{id}` | PARTIAL — transport controls are live; generic field editor is not exposed |
| Transport mode / transport rows | `/transport-mode`, `/transports` | DONE |
| Backhaul install/status | backhaul routes | DONE |
| MTunnel install/health/repair | mtunnel routes | DONE |
| SSH tunnel install | `/ssh/install` | DONE |
| Provision new node | `/v1/provision/install` | DONE |
| SSH preflight | `/v1/provision/test` | DONE |
| Protocol health/repair/restart | provision protocol routes | DONE |
| Upgrade agent / install fabric / fabric status | provision routes | DONE |
| Quota commands/config/sessions | node quota routes | TODO dedicated admin UI |

## Domains / branding / settings

| Capability | Contract | Status |
|---|---|---|
| Domains CRUD | `/v1/admin/domains*` | DONE |
| Automatic SSL | `/v1/admin/domains/{id}/ssl` | DONE |
| Domain roles panel/shop/api/subscription | domain model | DONE |
| Branding | `/v1/settings/branding` | DONE live component |
| L2TP settings / PSK generation | `/v1/settings/vpn/l2tp*` | DONE live component |
| Subscription username settings | `/v1/settings/general/subscription-username` | DONE |
| Other general settings | `/v1/settings/general/*` | PARTIAL — only proven live settings are exposed |
| Notification settings/test | `/v1/settings/notifications*` | DONE |
| Mother access global/reseller override | `/v1/mother-access/admin*` | DONE |

## Commerce / finance

| Capability | Contract | Status |
|---|---|---|
| Payments list | `/v1/payments/admin/intents` | DONE |
| Approve/reject | payment admin routes | DONE |
| Receipt-specific admin workflow | payment receipt routes | PARTIAL — core review actions are live |
| Payment settings | `/v1/payments/admin/settings` | PARTIAL — SMS/payment matching settings are live |
| SMS Reader | `/v1/payments/admin/sms-reader*`, `/v1/payments/sms-reader/*` | DONE core |
| Pair code / Automagen device / revoke | SMS Reader routes | DONE |
| Customer wallets | `/v1/admin/wallet/*` | DONE core operations |
| Wallet top-up approve/reject | wallet admin routes | DONE |
| Wallet adjustment | wallet admin route | DONE |
| Discounts CRUD | `/v1/discounts/admin*` | DONE core CRUD |
| Store orders admin queue | `/v1/store/orders*` | TODO dedicated admin UI |
| Storefront settings | `GET/PUT /v1/storefront/settings` | DONE live editor |

## Resellers

| Capability | Contract | Status |
|---|---|---|
| Admin reseller list/stats/create/toggle/delete | `/v1/admin/resellers*` | DONE core |
| Reseller wallet adjustment | admin reseller wallet route | DONE |
| Per-plan pricing | admin reseller plans routes | PARTIAL — API client present; detailed admin editor still pending |
| Traffic balance/transactions/adjust | reseller traffic routes | PARTIAL — portal live; detailed admin tooling still pending |
| Reseller portal dashboard | `/v1/reseller/dashboard` | DONE |
| Customers list/create | reseller customer routes | DONE core |
| Sell subscriptions | reseller subscription route | DONE |
| Subscription management / connection info | reseller subscription routes | DONE core |
| Reseller wallet | reseller wallet routes | DONE |
| Reseller traffic | reseller traffic routes | DONE |
| Reseller orders / sales | reseller commerce routes | DONE core |
| Reseller bot | `/v1/reseller/bot*`, bot-commerce routes | DONE core runtime |
| Reseller notifications | reseller notification routes | DONE core runtime |
| Reseller settings | reseller settings/profile routes | DONE core runtime |

## Telegram / support / notifications

| Capability | Contract | Status |
|---|---|---|
| Main Telegram bot status | `/v1/admin/telegram-bot` | DONE |
| Save token/test/install/start/stop/restart/logs | telegram bot routes | DONE |
| Telegram user links / sessions | `/v1/telegram/*` | DONE through Telegram Manager |
| Support admin inbox | `/v1/admin/support/tickets*` | DONE core |
| Admin reply/close/reopen/delete | support admin routes | DONE |
| Customer support | `/v1/support/tickets*` | DONE core runtime |
| Guest support | `/v1/support/guest/tickets*` | TODO public guest flow |
| User notifications | `/v1/notifications/*` | DONE core runtime |
| Admin panel notifications | `/v1/admin/panel-notifications*` | DONE |
| Admin send/history | `/v1/admin/notifications/*` | DONE |
| Notification settings/test | `/v1/settings/notifications*` | DONE |

## Backup / recovery

| Capability | Contract | Status |
|---|---|---|
| List backups | `GET /v1/admin/backups` | DONE |
| Manual backup | `POST /v1/admin/backups/create` | DONE |
| Schedule/retention/Telegram settings | `PUT /v1/admin/backups/settings` | DONE |
| Telegram test/send | backup routes | DONE |
| Restore/delete | backup routes | DONE |
| Inspect backup | backup info route | DONE |
| Upload backup | `/v1/admin/backups/upload` | DONE |
| Authenticated download | backup download route | DONE |
| Recovery key download | backup recovery-key route | DONE |

## Customer portal / delivery

| Capability | Contract | Status |
|---|---|---|
| Dashboard | customer APIs | DONE core |
| Subscription management | `/v1/customer/subscriptions/{id}/manage` | DONE core |
| Connection info | connection-info route | DONE |
| Subscription link | connection info | DONE |
| QR / File | public connect + connection info | DONE core |
| Account username/password | connection info | DONE |
| Usage | subscription/public usage | DONE core |
| Orders/payments | customer store/payment routes | DONE core |
| Wallet | customer wallet routes | DONE core |
| Profile / 2FA | auth routes | DONE core |
| Online support/chat | support routes | DONE core |
| Notifications | user notification routes | DONE core |
| Offline downloads | migrated server assets `/downloads/apps/*` | UI ready; ASSET MIGRATION REQUIRED |

## Store / learning center

| Capability | Status |
|---|---|
| Public navigation / mobile drawer | DONE |
| FA/EN + Dark/Light | DONE base |
| Public plans | DONE — backend driven |
| Protocols / guides / FAQ | DONE UI |
| Real store order creation | DONE |
| Login/register return to pending store flow | DONE |
| Discount + payment hand-off | PARTIAL — requires production E2E validation |
| Legacy learning content | MIGRATED STRUCTURE |
| Legacy app images | migration script; binary assets not in Git |
| Offline installers | migration script; binaries stay on server |

## Backup-safe migration / deployment

| Capability | Status |
|---|---|
| UI build in GitHub Actions | DONE |
| Source contains no production `.env` or private keys | DONE by repository policy |
| Release/install workflow | PARTIAL — installer/release packaging remains a separate deployment milestone |
| Database migration baseline | TODO — production backend still needs an explicit Alembic baseline before schema evolution |

## Remaining intentional gaps before production cutover

1. Dedicated Quota administration UI for command/config/session inspection.
2. Dedicated admin Store Orders queue and receipt-oriented review refinements.
3. Full node edit/delete lifecycle UI and generic tunnel PATCH editor.
4. Detailed admin reseller per-plan pricing and traffic tooling.
5. Public guest support flow.
6. Production E2E checkout/payment/discount verification.
7. Migration of offline application binaries and legacy image assets on the destination server.
8. Backend Alembic baseline and release/installer packaging.

## Migration-only assets

- Old learning images: `public/learning/apps/*`
- Old offline clients: `/opt/moviline-downloads/apps/*`
- Never copy `.env`, DB passwords, Telegram tokens, SSH private keys, `tp27-pki/*.key`, backups, candidate files, `.next`, `node_modules`.
