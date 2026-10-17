# TwinPanel Installation Guide

This guide covers the official self-hosted installation. Customer installations come from the public `matin111/twinpanel` repository and its validated Stable manifest, never from experimental feature/fix branches.

## Requirements

- Clean Ubuntu 22.04 or 24.04 server
- root access
- 2GB RAM and 2 vCPU recommended
- At least 20GB free disk space
- Outbound Internet access for installation/update downloads
- Ports 80 and 443 for the public web endpoint

## Quick install

Run one command as root or through sudo:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/twinpanel/main/install.sh | sudo bash
```

No GitHub account, SSH key, Deploy Key, Personal Access Token, manual clone, branch selection, or commit selection is required from the customer.

The bootstrap reads the public Stable manifest at:

```text
https://raw.githubusercontent.com/matin111/twinpanel/main/releases/stable.json
```

The manifest points to one validated public Git commit. The installer fetches that exact commit over HTTPS and verifies the checked-out commit before installation. Customer installations therefore do not float with every new commit pushed to `main`.

## Installation flow

1. Validate the supported Ubuntu release and root access
2. Resolve the published Stable release manifest
3. Read the exact release version and source commit
4. Fetch the public TwinPanel repository over HTTPS
5. Verify the checked-out Git commit against the manifest
6. Verify the source `VERSION`
7. Install PostgreSQL, Redis, Python runtime, Node.js, Nginx, and dependencies
8. Install Backend and Frontend
9. Generate local secrets with restricted permissions
10. Initialize the database and bootstrap the initial admin
11. Install systemd services
12. Install the `twinpanel` / `tp` SSH management menu
13. Enable Nginx and services
14. Run final Web/API health checks

## Initial admin credentials

The installer generates a random initial administrator password and stores it only in the root-only file below with mode `0600`:

```text
/root/twinpanel-initial-admin.txt
```

This account is for the first login. After signing in, change the administrator email/password and remove the initial credentials file.

Reinstalling or updating TwinPanel preserves an existing administrator instead of silently replacing the admin password.

## SSH management

After installation run:

```bash
twinpanel
```

or:

```bash
tp
```

The SSH menu provides panel/service status, admin management, protocol management, updates, backup, logs/diagnostics, version information and related operational controls.

## Domain and SSL

A domain is not required during the first installation. TwinPanel can start on the server public IP. Domains and TLS can be configured later from the product controls.

## Updates

The panel reads the same public Stable manifest used for installation. When a newer validated release is published, the update process uses the exact source commit declared by the manifest.

The guarded update path includes:

- pre-update backup
- exact release commit fetch over HTTPS
- Git commit verification
- version verification
- dependency install/build
- atomic `/opt/twinpanel/current` switch
- service restart
- Web/API health verification
- automatic rollback to the previous release when health verification fails

## Licensing

The current public `1.1.0-rc.1` manifest is installable without a mandatory license service (`license_required: false`). The product retains its license/trial integration so a vendor license service can be enabled later without changing the customer-facing one-line installation command.

## Important paths

```text
/opt/twinpanel/current                 active release
/opt/twinpanel/releases                installed releases
/opt/twinpanel/venv                    Python virtual environment
/etc/twinpanel/backend.env             backend runtime environment
/etc/twinpanel/frontend.env            frontend runtime environment
/etc/twinpanel/install.env             release/install settings
/var/lib/twinpanel-backups             backups
/var/lib/twinpanel-license             release/license/update state
/root/twinpanel-initial-admin.txt      initial admin credentials
/usr/local/bin/twinpanel               SSH management command
/usr/local/bin/tp                      short SSH management alias
```

## Security rule

Never commit production secrets, vendor signing private keys, SSH private keys, Telegram tokens, production environment files, certificate private keys, database dumps, or confidential customer data to GitHub.
