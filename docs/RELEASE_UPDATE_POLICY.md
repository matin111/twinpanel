# TwinPanel Release and Update Policy

## Canonical branches

Customer installations must never install directly from a development branch.

Keep only these long-lived branches after migration:

- `main` — reviewed source history / development integration
- `release/stable-v1` — exact candidate for the next customer release
- `product/self-hosted-v1` — temporary compatibility branch until all required product logic is promoted into `release/stable-v1`

All short-lived `feat/*`, `fix/*`, `deploy/*`, `preview/*`, `preserve/*`, `backup/*`, and `ci/*` branches must be deleted after their commits are either merged into the canonical release or explicitly archived/tagged.

Never delete an unmerged branch only because it looks old. First verify whether it contains commits not reachable from `release/stable-v1`.

## Versioning

The root `VERSION` file is authoritative for the product version.

Release channels:

- `preview` — developer/test only
- `candidate` — release candidate / clean-install validation
- `stable` — customer-installable

Recommended promotion:

```text
1.1.0-preview.N -> 1.1.0-rc.N -> 1.1.0
```

## Stable release gates

A Stable version may be published only after:

1. Frontend TypeScript/build succeeds
2. Backend compile/import succeeds
3. Clean PostgreSQL schema bootstrap succeeds
4. Redis connectivity succeeds
5. Initial admin bootstrap succeeds
6. Web/API health checks pass
7. Every admin menu route resolves to the intended current component
8. Installer passes `bash -n` / shellcheck
9. Clean install on supported Ubuntu succeeds
10. Update from previous Stable succeeds
11. Failed update rollback is tested
12. Backup/restore integrity test passes
13. Trial activation and paid-license conversion are tested

## Release manifest

A small public manifest may be cached publicly and contains only non-sensitive metadata:

```json
{
  "product": "TwinPanel",
  "channel": "stable",
  "version": "1.1.0",
  "published_at": "2026-10-17T00:00:00Z",
  "minimum_updater_version": 1,
  "notes_fa": "...",
  "notes_en": "...",
  "license_required": true
}
```

The actual package download URL is not placed in the public manifest when customer access is licensed. The updater requests an expiring entitled download URL from the vendor license/distribution API.

## In-panel update behavior

The admin UI checks for a newer release at a bounded interval and also supports manual refresh. When an update is available it displays:

- installed version
- latest entitled version
- publication time
- Persian/English release notes
- update state
- Update button

Pressing Update must not run `git pull` on a customer server. It launches the local release updater, which:

1. obtains an update lock
2. creates a pre-upgrade backup
3. requests an entitled package URL
4. downloads to a temporary path
5. verifies SHA256/signature metadata
6. extracts into a new immutable release directory
7. installs dependencies and builds
8. performs migrations/bootstrap checks
9. switches `/opt/twinpanel/current` atomically
10. restarts services
11. verifies health/readiness
12. rolls back the symlink and restarts the prior release if health fails

## Admin notification

The panel should create one deduplicated admin notification when a newer entitled Stable release becomes available. Repeated checks must update the same notification rather than creating notification spam.

## Footer

Every admin page should show a compact footer containing:

- `TwinPanel vX.Y.Z`
- license/trial status
- update status badge
- GitHub project link

The footer must not display secrets, installation tokens, or license keys.

## Branch cleanup

After `release/stable-v1` is verified, remote branch cleanup must use Git reachability rather than wildcard deletion.

Safe principle:

```text
Delete only short-lived branches that are already merged/reachable from the canonical release or explicitly preserved by an annotated tag.
```

This prevents GitHub from remaining crowded without losing unmerged work.
