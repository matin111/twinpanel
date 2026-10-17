# TwinPanel Release Workflow

This repository uses one canonical customer release line. Experimental branches must never become install sources.

## Canonical branches

- `release/stable-v1` — customer-installable source of truth.
- `feat/*`, `fix/*`, `deploy/*`, `preview/*` — temporary development/integration branches only.

## Versioning

- Product version lives in `VERSION`.
- Release candidates use `X.Y.Z-rc.N`.
- Stable releases use `X.Y.Z`.
- Every published stable manifest must reference exactly one validated release artifact SHA256.

## Promotion flow

1. Develop on one focused branch.
2. Open a PR into `release/stable-v1`.
3. CI must build Frontend, compile/import Backend, validate installer/update scripts, bootstrap a clean schema, and run API health checks.
4. Merge only after CI passes.
5. Build the customer artifact from the merged release commit.
6. Publish the artifact to the private distribution store.
7. Update the public `tp27-core/twinpanel/releases/stable.json` manifest with version/release notes only.
8. License service resolves an entitled, expiring package URL for each installation.

## Customer update behavior

The panel checks the public stable manifest and shows an update badge when a newer version exists. The Update button triggers the root-owned updater service. The updater:

- validates current license/trial entitlement
- creates a pre-update encrypted backup
- asks the vendor service for the entitled release URL
- verifies SHA256
- installs into `/opt/twinpanel/releases/<version>`
- builds before switching the active symlink
- atomically moves `/opt/twinpanel/current`
- restarts services
- verifies API/Web health
- rolls back automatically if health fails
- keeps a small number of prior releases

## License behavior

- New installs request a 7-day trial when no paid key is supplied.
- Trial is server-authoritative and bound to the installation fingerprint.
- Paid activation upgrades the same installation in place.
- Temporary license-server outages use a bounded offline grace period.
- Expiry does not abruptly terminate existing VPN traffic.
- Admin backup/export, diagnostics, and license activation remain accessible after expiry.
- New protected management mutations are blocked after authoritative expiry.

## Repository cleanup

After a release is validated and deployed, temporary branches that are fully contained in the canonical release branch should be removed. Preserve only branches needed for active work, audit, rollback, or unresolved production investigation.

Do not delete old branches before the release commit is verified on a clean install and on an upgrade from the previous stable release.
