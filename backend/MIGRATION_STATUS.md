# TwinPanel Backend Clean Migration

This draft branch migrates the working legacy TwinPanel/VPNShop runtime into the clean 2027 repository without bringing historical backups, secrets, PKI, database dumps, candidate files, or frontend patch CSS.

## Current status

### Completed scaffolding

- Python 3.12 dependency manifest is pinned under `backend/requirements.txt`.
- Production-safe `.env.example` contains names/placeholders only.
- `scripts/import-legacy-backend-clean.sh` copies only the live `app/` runtime and rejects historical/sensitive files.
- `scripts/export-legacy-backend-clean.sh` creates a clean uploadable backend bundle on the legacy server without requiring GitHub credentials there.
- `scripts/import-backend-export.sh` re-validates an export archive before replacing `backend/app` in a migration branch.
- Export/import reject `.env`, private keys/certificates, database dumps, candidate/history files and obvious embedded credentials, compile Python and create SHA-256 manifests.
- Healthy Quota Agent code can be exported/imported as `quota-agent/`, but `config.json`, PKI, state, certificates and private keys are deliberately excluded.
- Quota Agent systemd packaging is optional and only starts when a real local `/etc/twinpanel-quota-agent/config.json` exists and its `client_cert`, `client_key` and `ca_cert` files are present.
- `backend/create_admin.py` creates or promotes the administrator using the real `User`, `UserRole.ADMIN`, `SessionLocal` and `hash_password` contracts.
- Static CI rejects private material and forbidden files, compiles Python bootstrap/runtime/Quota Agent code, validates dependencies, syntax-checks installer/migration shell scripts and validates clean deployment templates.
- systemd templates bind Web/API to `127.0.0.1` only.
- Nginx proxies `/v1`, `/health` and `/install` to the API and the remaining site to Next.js.
- Installer generates application/agent/payment/database secrets under `/etc/twinpanel` with root-only permissions.
- Reseller Bot encryption key is generated locally with Fernet and stored as `/etc/twinpanel-reseller-bot.key` mode `0600`; the old server key is never copied or committed.
- Installer supports configurable domain, Web port, API port, Admin display name/email/password, license key and optional Let's Encrypt HTTPS.
- Release layout is `/opt/twinpanel/releases/<version>-<timestamp>` with atomic `/opt/twinpanel/current` symlink.
- Verified runtime workers are release-aware: `twinpanel-transport-manager`, `twinpanel-reseller-bots` and `twinpanel-backup.timer` are installed when their real modules exist.
- `twinpanel-bot` unit is installed when its runtime exists but is only started after `/etc/twinpanel-telegram-api.env` is configured.
- Optional `twinpanel-quota-agent` follows the active release but never receives its mTLS material from Git.
- Obsolete `vpnshop-relay-manager` is explicitly disabled/removed; the V3 `twinpanel-transport-manager` remains the single writer for tunnel transport state.
- VPN Node Agent remains node-local and is installed/upgraded through the verified provisioning flow instead of being treated as a central service.
- Legacy receipt-cleanup workers are intentionally not packaged as healthy workers because production audit evidence showed failures; they must be separately fixed and re-verified before inclusion.
- Update creates a PostgreSQL dump before database migration and switches API/Web/workers atomically to the new release. Failed health checks switch code/runtime back automatically.
- Rollback restores API/Web/worker units together and never restores the database automatically.
- Repair is non-destructive, re-renders service/Nginx config and re-installs verified workers without mutating database schema.
- Healthcheck validates PostgreSQL, Redis, Nginx, API, Web, expected workers/timers, optional Quota Agent readiness, local API/Web routes and confirms obsolete relay-manager inactivity.
- Uninstall stops/removes API/Web/worker units and preserves DB/backups/secrets by default; purge/drop-database require separate explicit confirmation.
- Maintenance CLI is provided as `twinpanel status|health|repair|rollback|update PATH|logs|version|uninstall` after successful installation.

### Still pending — do not mark this PR ready yet

- The actual verified legacy Python runtime has not yet been imported into `backend/app` in Git.
- Runtime import/`app.main` smoke test has not yet been executed from this repository.
- `/health` and OpenAPI route parity have not yet been validated against the migrated runtime.
- An Alembic baseline for the verified production schema has not yet been created.
- Quota Agent source packaging is ready, but a fresh-install PKI enrollment/bootstrap flow is not yet implemented; existing valid local mTLS configuration can be reused during migration.
- VPN Node Agent remains provisioned remotely by the backend and still needs final clean-runtime smoke validation after `backend/app` is imported.
- Failed receipt-cleanup workers are excluded until their database/model issue is fixed and verified.
- License-server validation/download/signature verification is a later release milestone; the installer currently stores the supplied license key securely but does not pretend to validate it remotely.

## Required gates before merge

1. All live runtime Python files are present under `backend/app`.
2. `python3 -m compileall -q backend/app` passes.
3. Dependencies install cleanly on Python 3.12.
4. `app.main` import smoke test passes against an isolated/migration-safe environment.
5. FastAPI `/health` works with PostgreSQL and Redis available.
6. OpenAPI route parity is checked against the verified legacy feature surface.
7. Database evolution uses an Alembic baseline generated from the verified existing schema; do not guess/recreate the live schema.
8. No `.env`, private keys, certificates, database dumps, SSH credentials, bot tokens or runtime secrets are committed.
9. Installer/static deployment checks remain green after the real backend runtime is imported.
10. Verified runtime workers start from `/opt/twinpanel/current`; `vpnshop-relay-manager` remains inactive.
11. If Quota Agent code is included, its Git tree contains no config/PKI/state and it only starts with verified local mTLS files.

## Preferred migration path: safe export from old server

On the old server, create the clean archive with:

```bash
cd /path/to/private-twinpanel-clone
git checkout feat/backend-runtime-import-final
git pull --ff-only
sudo bash scripts/export-legacy-backend-clean.sh /root/vpnshop/vpnshop /root
```

Expected output ends with:

```text
COMPILE_OK
CLEAN_NAMES_OK
SECRET_SCAN_OK
RUNTIME_FILE_COUNT=<number>
QUOTA_AGENT_FILE_COUNT=<number>
EXPORT=/root/twinpanel-backend-clean-<timestamp>.tar.gz
SHA256=<sha256>
CLEAN_BACKEND_EXPORT_READY
```

Upload only that generated `.tar.gz` for review/import. Never upload the project `.env`, Quota PKI/config, database dump, Telegram token files, SSH credentials, `/etc/twinpanel*` secrets or backup archives.

To import the reviewed archive into a private migration clone:

```bash
cd /path/to/twinpanel-clone
git checkout feat/backend-runtime-import-final
bash scripts/import-backend-export.sh /path/to/twinpanel-backend-clean-*.tar.gz "$PWD"
git status --short backend quota-agent
```

Expected output includes `BACKEND_EXPORT_IMPORTED`. Before any commit, inspect `backend/RUNTIME_MANIFEST.sha256`, optional `quota-agent/QUOTA_AGENT_MANIFEST.sha256`, and the full Git diff.

## Alternate migration path: direct clean import on old server

If the private repository is already cloned on the old server:

```bash
cd /path/to/twinpanel-clone
git checkout feat/backend-runtime-import-final
git pull --ff-only
bash scripts/import-legacy-backend-clean.sh /root/vpnshop/vpnshop "$PWD"
git status --short backend
```

Expected output includes:

```text
COMPILE_OK
CLEAN_NAMES_OK
RUNTIME_FILE_COUNT=<number>
CLEAN_BACKEND_IMPORT_READY
```

Do not bypass a forbidden-file or secret-scan failure.

## Confirmed legacy feature surface

- Auth and 2FA
- Users and administration
- Plans and subscriptions
- Nodes and provisioning
- Tunnels and V3 transport manager
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

The verified legacy runtime currently calls `Base.metadata.create_all`. The clean product must move to an Alembic baseline generated from the verified existing schema before normal schema-changing releases.

Installer behavior is deliberately conservative:

- Empty database + no Alembic: the verified imported runtime may bootstrap its initial schema.
- Existing non-empty database + Alembic: run `alembic upgrade head`.
- Existing non-empty database + no Alembic: stop by default. A one-time `TWINPANEL_ALLOW_EXISTING_SCHEMA=1` override is available only after the operator has explicitly verified exact schema compatibility; it does **not** run `create_all` during update.

Existing production data must never be recreated from model guesses.
