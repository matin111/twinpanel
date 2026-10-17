# TwinPanel Installation Guide

This guide covers the official self-hosted installation. Customer installations must come only from the official release channel, never from experimental feature/fix branches.

## Requirements

- Clean Ubuntu 22.04 or 24.04 server
- root access
- 2GB RAM and 2 vCPU recommended
- At least 20GB free disk space
- Outbound Internet access for install/update downloads
- Ports 80 and 443 for the public web endpoint

## Quick install

The public bootstrap command is hosted in `matin111/tp27-core`. The public bootstrap contains no private TwinPanel source or vendor signing secrets; it resolves the entitled release through the license/distribution service.

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/tp27-core/main/twinpanel/install.sh | sudo bash
```

If no paid License Key is entered, the installer requests a seven-day trial for the installation. The trial starts on the first successful activation and must not reset when local files are removed or TwinPanel is reinstalled.

## Installation flow

1. Validate OS, resources, and ports
2. Generate an Installation ID and machine fingerprint
3. Activate a paid license or seven-day trial
4. Resolve the newest entitled release for the installation
5. Verify package SHA256
6. Install PostgreSQL, Redis, Python runtime, Node.js, Nginx, and dependencies
7. Install Backend and Frontend
8. Generate local secrets with restricted permissions
9. Initialize the database and bootstrap the initial admin
10. Install systemd services
11. Enable Nginx
12. Run final Web/API/DB/Redis health checks

## Initial admin credentials

The installer generates a random initial administrator password and stores it only in the root-only file below with mode `0600`:

```text
/root/twinpanel-initial-admin.txt
```

After the first login, change the email/password and delete the file.

## Domain and SSL

A domain is not required during the first installation. TwinPanel can start on the server public IP. Domains and TLS are managed later from the Domains & SSL section.

## Updates

The admin panel displays the installed version and update state. When a newer Stable release is available, an update notification appears. Pressing Update runs a guarded process:

- pre-upgrade backup
- entitled release download
- checksum verification
- build/install the new release
- service restart
- health verification
- automatic rollback on failure

## Trial and license

- Trial duration: exactly 7 days from the first successful activation
- 3 days remaining: visible warning
- 24 hours remaining: persistent warning
- Trial expired: admin login, license activation, backup/export and diagnostics remain accessible; new management mutations are restricted according to license policy
- A temporary license-server outage must not abruptly terminate existing VPN user traffic; a bounded offline grace window is used for connectivity failures

## Important paths

```text
/opt/twinpanel/current                 active release
/opt/twinpanel/releases                installed releases
/etc/twinpanel/backend.env             backend runtime environment
/etc/twinpanel/frontend.env            frontend runtime environment
/var/lib/twinpanel-backups             backups
/var/lib/twinpanel-license             local license state
/root/twinpanel-initial-admin.txt      initial admin credentials
```

## Security rule

Never commit tokens, vendor license signing keys, SSH private keys, Telegram tokens, production environment files, certificates/private keys, or database dumps to GitHub.
