# TwinPanel Backend Clean Migration

## Source

The runtime source was exported from the legacy TwinPanel/VPNShop server and cleaned before migration.

## Validation completed

- 110 runtime files selected from the legacy export.
- Historical `*.bak*`, `*.bad*`, `*.old*`, `*.disabled*`, `*candidate*`, `__pycache__` and `*.pyc` files excluded.
- Historical zeroed provisioning copy excluded.
- No private-key blocks or obvious hard-coded production secrets detected in the clean runtime tree.
- `python3 -m compileall -q app` passed on the clean runtime tree before migration.

## Migration policy

Do not merge this branch to `main` until all runtime source is present and the following gates pass:

1. Python compile check.
2. Dependency installation in a clean virtual environment.
3. Import smoke test for `app.main`.
4. FastAPI `/health` smoke test with PostgreSQL and Redis available.
5. OpenAPI route parity check against the legacy runtime.
6. Database schema migration plan approved. The legacy application currently calls `Base.metadata.create_all`; production evolution must move to an Alembic baseline without rebuilding or guessing the live schema.
7. No `.env`, private keys, PKI material, database dumps, SSH credentials or runtime secrets committed.

## Current repository migration state

Core bootstrap files have started migrating under `backend/`. The complete clean runtime tree is intentionally kept on this feature branch until validation is complete.

## Confirmed legacy feature surface

- Authentication and 2FA
- Users and administration
- Plans and subscriptions
- Nodes and provisioning
- Tunnels and transport management
- Quota enforcement
- Payments and SMS Reader
- Customer wallet
- Store and storefront settings
- Discounts
- Resellers and reseller bot commerce
- Telegram management and bots
- Support and notifications
- Domains and SSL
- Branding and general settings
- VPN settings
- Mother access
- Account delivery
- Backup and restore
