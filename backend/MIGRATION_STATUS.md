# TwinPanel Backend Clean Migration

## Source

The runtime source was exported from the legacy TwinPanel/VPNShop server and cleaned before migration.

## Validation completed

- 109 files are present under `backend/app` in the cleaned runtime tree, plus the pinned `requirements.txt` dependency set.
- Historical `*.bak*`, `*.bad*`, `*.old*`, `*.disabled*`, `*candidate*`, `__pycache__` and `*.pyc` files are excluded.
- Historical zeroed/before copies are excluded.
- No private-key blocks or obvious hard-coded production secrets were detected in the cleaned runtime tree.
- `python3 -m compileall -q app` passed before repository import.

## Migration policy

Do not merge this branch to `main` until these gates pass:

1. Python compile check.
2. Dependency installation in a clean Python 3.12 environment.
3. Import smoke test for `app.main`.
4. FastAPI `/health` smoke test with PostgreSQL and Redis available.
5. OpenAPI route parity check against the verified legacy runtime.
6. Database schema migration plan approved. The legacy application currently calls `Base.metadata.create_all`; production evolution must move to an Alembic baseline without rebuilding or guessing the live schema.
7. No `.env`, private keys, PKI material, database dumps, SSH credentials or runtime secrets committed.

## Confirmed feature surface

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
