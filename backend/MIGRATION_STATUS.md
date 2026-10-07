# TwinPanel Backend Clean Migration

This branch migrates the working legacy TwinPanel/VPNShop runtime into the clean 2027 repository without bringing historical backups, secrets, PKI, dumps, candidate files, or frontend patch CSS.

## Required gates before merge

1. All runtime Python files are present under `backend/app`.
2. `python3 -m compileall -q backend/app` passes.
3. Dependencies install cleanly on Python 3.12.
4. `app.main` import smoke test passes.
5. FastAPI `/health` works with PostgreSQL and Redis available.
6. OpenAPI route parity is checked against the verified legacy feature surface.
7. Database evolution uses an Alembic baseline; do not guess or rebuild the live schema.
8. No `.env`, private keys, certificates, database dumps, SSH credentials, bot tokens or runtime secrets are committed.

## Confirmed legacy feature surface

- Auth and 2FA
- Users and administration
- Plans and subscriptions
- Nodes and provisioning
- Tunnels and transport manager
- Quota/session enforcement
- Payments and SMS Reader
- Customer wallet
- Store/storefront settings
- Discounts
- Resellers and reseller bot commerce
- Telegram management and bots
- Support and notifications
- Domains and SSL
- Branding/general settings
- VPN settings
- Mother access
- Account delivery
- Backup/restore

## Database policy

The legacy runtime currently calls `Base.metadata.create_all`. The clean product must move to an Alembic baseline generated from the verified existing schema. Existing production data must never be recreated from model guesses.
