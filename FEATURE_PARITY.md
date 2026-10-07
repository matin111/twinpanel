# TwinPanel 2027 — Legacy Feature Parity Matrix

This file is the migration contract. A feature is not considered migrated just because a menu item exists. `DONE` means the new UI calls the real legacy-compatible backend endpoint and no sample business data is shown.

## Rules

- Preserve the 2027 visual system; do not replace live features with simplified placeholder UI.
- Never ship fake users, servers, balances, orders, domains, bot names, backup files, or revenue.
- Reuse the proven backend contracts and database; do not invent a parallel schema.
- Public store remains public. Customer/Admin/Reseller operations remain role protected.
- Production domains come from Domains & SSL; no customer domain is hard-coded.
- Secrets, private keys, backups and offline application binaries are never committed to Git.

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

## Admin dashboard / system

| Capability | Contract | Status |
|---|---|---|
| Dashboard stats | `/v1/admin/stats`, `/v1/admin/dashboard-summary` | DONE |
| Revenue chart | real admin payment intents | DONE |
| Subscription donut | real subscriptions | DONE |
| Nodes/tunnels widgets | `/v1/nodes`, `/v1/tunnels` | DONE |
| Protocol health | `/v1/admin/dashboard-summary`, `/v1/admin/core-protocols` | PARTIAL |
| System health | `/v1/admin/system-health` | TODO |
| Security overview | `/v1/admin/security/overview` | TODO |

## Users / subscriptions / plans

| Capability | Contract | Status |
|---|---|---|
| Users list/create/edit/delete | `/v1/admin/users*` | DONE |
| Toggle/reset password | admin user routes | DONE |
| Subscriptions list | `/v1/subscriptions` | DONE (list) |
| Create/edit/activate/suspend/delete | subscription admin routes | TODO operations |
| Extend/manual limits | subscription admin routes | TODO |
| Provision/refresh credentials | subscription admin routes | TODO |
| Plans list | `/v1/plans/admin/all` | DONE (list) |
| Plans CRUD | `/v1/plans*` | TODO operations |

## Nodes / tunnels / provisioning

| Capability | Contract | Status |
|---|---|---|
| Nodes list | `/v1/nodes` | DONE (list) |
| Node CRUD / maintenance | `/v1/nodes*` | TODO operations |
| Node health/protocols | node health routes | TODO detail |
| Tunnels list | `/v1/tunnels` | DONE (list) |
| Tunnel CRUD/toggle/health | tunnel routes | TODO operations |
| Transport mode / transports | tunnel transport routes | TODO |
| Backhaul/MTunnel/SSH operations | tunnel install/repair routes | TODO |
| Provisioning | `/v1/provision/*` | MOCK UI — TODO |
| Quota commands/config/sessions | node quota routes | TODO |

## Domains / branding / settings

| Capability | Contract | Status |
|---|---|---|
| Domains CRUD | `/v1/admin/domains*` | DONE |
| Automatic SSL | `/v1/admin/domains/{id}/ssl` | DONE |
| Domain roles panel/shop/api/subscription | domain model | DONE |
| Branding | `/v1/settings/branding` | LIVE — VERIFY SAVE |
| L2TP settings | `/v1/settings/vpn/l2tp*` | LIVE — VERIFY FULL ACTIONS |
| General settings | `/v1/settings/general/*` | TODO |
| Notification settings/test | `/v1/settings/notifications*` | TODO |
| Mother access | `/v1/mother-access/admin*` | MOCK UI — TODO |

## Commerce / finance

| Capability | Contract | Status |
|---|---|---|
| Payments list | `/v1/payments/admin/intents` | DONE (list) |
| Approve/reject/receipt | payment admin routes | TODO operations |
| Payment settings | `/v1/payments/admin/settings` | TODO |
| SMS Reader | `/v1/payments/admin/sms-reader*`, `/v1/payments/sms-reader/*` | MOCK UI — TODO |
| Customer wallets | `/v1/admin/wallet/*` | DONE core operations |
| Wallet top-up approve/reject | wallet admin routes | DONE |
| Wallet adjustment | wallet admin route | DONE |
| Discounts CRUD | `/v1/discounts/admin*` | DONE core CRUD |
| Store orders | `/v1/store/orders*` | TODO admin UI |
| Storefront settings | `GET/PUT /v1/storefront/settings` | DONE generic live editor; refine labels |

## Resellers

| Capability | Contract | Status |
|---|---|---|
| Admin reseller list/stats/create/toggle/delete | `/v1/admin/resellers*` | DONE core |
| Reseller wallet adjustment | admin reseller wallet route | DONE |
| Per-plan pricing | admin reseller plans routes | TODO detail UI |
| Traffic packages/balance/transactions | reseller traffic routes | TODO detail UI |
| Reseller portal dashboard | `/v1/reseller/dashboard` | VERIFY / COMPLETE |
| Customers | reseller customer routes | VERIFY / COMPLETE |
| Sell/edit/extend/toggle subscriptions | reseller subscription routes | TODO full operations |
| Reseller bot | `/v1/reseller/bot*`, bot-commerce routes | TODO |
| Reseller notifications | reseller notification routes | TODO |

## Telegram / support / notifications

| Capability | Contract | Status |
|---|---|---|
| Main Telegram bot status | `/v1/admin/telegram-bot` | DONE |
| Save token/test/install/start/stop/restart/logs | telegram bot routes | DONE |
| Telegram user links / sessions | `/v1/telegram/*` | MOCK UI — TODO |
| Support admin inbox | `/v1/admin/support/tickets*` | VERIFY / COMPLETE |
| Customer support | `/v1/support/tickets*` | LIVE base; VERIFY messages/uploads |
| Guest support | `/v1/support/guest/tickets*` | TODO public flow |
| User notifications | `/v1/notifications/*` | LIVE base |
| Admin panel notifications | `/v1/admin/panel-notifications*` | VERIFY / COMPLETE |
| Admin send/history | `/v1/admin/notifications/*` | TODO |

## Backup / recovery

| Capability | Contract | Status |
|---|---|---|
| List backups | `GET /v1/admin/backups` | DONE |
| Manual backup | `POST /v1/admin/backups/create` | DONE |
| Schedule/retention/Telegram settings | `PUT /v1/admin/backups/settings` | DONE |
| Telegram test/send | backup routes | DONE |
| Restore/delete | backup routes | DONE |
| Upload backup | `/v1/admin/backups/upload` | TODO UI |
| Authenticated download | backup download route | TODO UI |
| Recovery key download | backup recovery-key route | TODO UI |

## Customer portal / delivery

| Capability | Contract | Status |
|---|---|---|
| Dashboard | customer APIs | DONE base |
| Subscription management | `/v1/customer/subscriptions/{id}/manage` | DONE base |
| Connection info | connection-info route | DONE |
| Subscription link | connection info | DONE |
| QR / File | public connect + connection info | DONE base |
| Account username/password | connection info | DONE |
| Offline downloads | migrated server assets `/downloads/apps/*` | UI ready; ASSET MIGRATION REQUIRED |
| Usage | subscription/public usage | LIVE base |
| Orders/payments | customer store/payment routes | LIVE base; VERIFY checkout |
| Wallet | customer wallet routes | LIVE base |
| Profile / 2FA | auth routes | DONE base |
| Online support/chat | support routes | LIVE widget; VERIFY attachment/emoji |

## Store / learning center

| Capability | Status |
|---|---|
| Public navigation / mobile drawer | DONE |
| FA/EN + Dark/Light | DONE base |
| Public plans/protocols/guides/FAQ | DONE UI; plans must remain backend-driven |
| Legacy learning content | MIGRATED STRUCTURE |
| Legacy app images | migration script; binary assets not in Git |
| Offline installers | migration script; binaries stay on server |
| Checkout / discounts / payment hand-off | TODO end-to-end verification |

## Migration-only assets

- Old learning images: `public/learning/apps/*`
- Old offline clients: `/opt/moviline-downloads/apps/*`
- Never copy `.env`, DB passwords, Telegram tokens, SSH private keys, `tp27-pki/*.key`, backups, candidate files, `.next`, `node_modules`.
