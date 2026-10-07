# Clean Migration Manifest

## Keep after source review
Auth + 2FA, users, plans, subscriptions/account delivery, nodes, tunnels/transports, provisioning, quota, payments/SMS reader, store/storefront, wallet, reseller portal/bot commerce, support, notifications, Telegram runtime, backup worker, branding/domain/general/VPN settings.

## Active runtime confirmed on old server
- `vpnshop-api.service`
- `twinpanel-web.service`
- `twinpanel-bot.service`
- `twinpanel-reseller-bots.service`
- `twinpanel-quota-agent.service`
- `twinpanel-transport-manager.service`
- backup/cleanup timers

## Never migrate
`*.bak*`, `*.backup*`, `*.broken*`, `*.candidate.py`, `.next`, `node_modules`, logs/caches, old CSS patch chains, private keys, secrets, old releases/candidates.

Backend Python files are not considered migrated until each source file and dependency is reviewed.
