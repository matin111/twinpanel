# TwinPanel Commercial Distribution

## Source of truth

All customer-installable TwinPanel application code lives in GitHub and is released from one validated canonical branch. Production servers must never become the source of truth.

Canonical customer release branch:

`release/stable-v1`

Temporary `feat/*`, `fix/*`, `deploy/*`, `preview/*`, preserve/backup branches are development or audit branches only and must not be used by customer installers.

## Repositories

### 1. `matin111/twinpanel` — private product source

Contains the customer product and release pipeline:

- `/app`, `/components`, `/lib`, `/public` — Next.js web application
- `/backend` — FastAPI API and runtime services
- `/installer` — release installation logic
- `/deploy/systemd` — service definitions
- `/deploy/nginx` — reverse proxy templates
- `/deploy` — runtime templates/examples
- database bootstrap/migrations
- health/diagnostic/update logic

No customer secret, vendor license signing private key, Telegram bot token, SSH private key, certificate private key, production `.env`, database dump, or customer backup may be committed.

### 2. `matin111/tp27-core` — public bootstrap and release metadata

Contains only public installation/bootstrap material, public license verification key, documentation links, and release-channel metadata. It does not contain the private TwinPanel product archive or vendor secrets.

The customer-facing one-line installer is:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/tp27-core/main/twinpanel/install.sh | sudo bash
```

### 3. Vendor license platform — separate private service/repository

The authoritative license service is not shipped to customer servers. Responsibilities:

- issue/revoke/suspend/extend paid licenses
- create/recover one 7-day trial per eligible installation fingerprint
- bind entitlement to installation/server identity
- activation and periodic validation API
- signed entitlement issuance
- permitted release channel/version
- time-limited private release download URLs
- license audit/events
- admin authentication and vendor Telegram bot
- activation reset/server move policy
- expiry notifications

All signing private keys and vendor bot secrets stay only in deployment secrets/environment variables on the vendor service.

## Customer install flow

1. Customer runs the public bootstrap installer.
2. Installer validates Ubuntu/resources/ports and generates a stable Installation ID.
3. Installer computes a privacy-conscious machine fingerprint locally.
4. With no paid key, the vendor API starts/recovers the 7-day trial. With a paid key, it activates the paid entitlement.
5. Vendor API returns a signed entitlement plus the permitted release metadata.
6. Installer obtains a short-lived download URL for the validated TwinPanel artifact.
7. Installer verifies SHA256 before extraction.
8. Installer sets up PostgreSQL, Redis, Backend, Frontend, systemd and Nginx.
9. Database schema and the one-time initial admin are created.
10. Installation succeeds only after Web/API/DB/Redis health checks pass.

## Runtime architecture

```text
Internet
   |
 Nginx :80/:443
   |--------------------> Next.js Web :3000
   |                         |
   |                         +--> same-origin /v1/*
   |
   +----------------------> FastAPI :8095
                              |
                    +---------+---------+
                    |                   |
              PostgreSQL :5432      Redis :6379
```

Browser requests remain same-origin. No hard-coded dependency on an old production panel/API is allowed.

## License architecture

Customer servers contain only:

- installation ID/fingerprint hash
- vendor API endpoint
- vendor public verification key
- signed entitlement/cache
- license/update UI and client logic

The customer server never receives the vendor signing private key.

Primary vendor API contract:

- `POST /v1/license/trial`
- `POST /v1/license/activate`
- `POST /v1/license/validate`
- `POST /v1/license/release`

Signed validation payloads include status, installation ID, expiry, edition/features, and release channel. A bounded offline grace period handles temporary vendor API outages.

After authoritative trial/license expiry, protected new management mutations are blocked, while admin login, license activation, backup/export and diagnostics remain available. Existing VPN data-plane traffic is not abruptly terminated by a temporary licensing outage.

## In-panel updates

Every customer panel displays its installed version and public GitHub/bootstrap link. The panel checks the public stable release manifest. When a newer entitled release exists, the administrator sees an update indicator and can press Update.

The root-owned updater service must:

1. validate entitlement
2. create an encrypted pre-update backup
3. request a time-limited entitled package URL
4. download and verify SHA256
5. install/build in `/opt/twinpanel/releases/<version>`
6. atomically switch `/opt/twinpanel/current`
7. restart services
8. verify Web/API health
9. roll back automatically on failure
10. keep only a small number of previous releases

## Telegram license bot

The vendor Telegram bot runs only on the vendor license server and is separate from customer sales bots. Minimum restricted/audited actions:

- `/newlicense`
- `/license <key>`
- `/extend <key>`
- `/suspend <key>`
- `/revoke <key>`
- `/resetactivation <key>`
- `/trial <installation_id>`
- `/trialinfo <installation_id>`
- `/resettrial <installation_id>`
- `/expiring`
- `/stats`

## Release gates

A customer release cannot be promoted unless CI verifies:

1. frontend build
2. backend compile/import
3. clean database bootstrap
4. login/bootstrap flow
5. API health/readiness
6. frontend-to-API proxy
7. installer/updater syntax
8. install on clean supported Ubuntu
9. upgrade from previous release
10. pre-update backup, rollback and health paths

## Repository hygiene

After a validated release is promoted and deployed, temporary branches fully contained by the canonical release should be removed. Keep only active work, release branches, necessary audit/preserve references, and unresolved incident branches. Do not delete historical branches until clean-install and upgrade tests prove the canonical release contains the required changes.

## Non-negotiable rule

Do not patch a customer production backend as a substitute for updating GitHub source. Every production fix must first exist in the canonical product source/release and then be deployed through the update mechanism.
