# TwinPanel Commercial Distribution

## Source of truth

All installable TwinPanel application code lives in GitHub and is released from a validated product branch/tag. Production servers must never become the source of truth.

Current product integration branch:

`product/self-hosted-v1`

This branch contains both:

- Next.js frontend
- FastAPI backend
- installer/deployment files
- node-agent/bootstrap code

## Repositories

### 1. `matin111/twinpanel`

Customer-installable product source and release pipeline.

Required release contents:

- `/app`, `/components`, `/lib`, `/public` — web application
- `/backend` — FastAPI API and all runtime services
- `/installer` — one-command installer/updater/repair/uninstaller
- `/deploy/systemd` — service definitions
- `/deploy/nginx` — reverse proxy templates
- `/deploy` — PostgreSQL/Redis/runtime deployment templates
- node-agent/bootstrap logic
- database bootstrap/migrations
- health/diagnostic scripts

No customer secret, license signing secret, Telegram bot token, SSH private key, certificate private key, production `.env`, or database dump may be committed.

### 2. License platform repository (private)

License server source must be stored in a separate private GitHub repository and deployed only on the vendor license server. It is not shipped inside customer installations.

Responsibilities:

- issue/revoke/suspend/extend licenses
- bind a license to an installation/server fingerprint according to policy
- activation and periodic validation API
- installation entitlement and release-channel response
- license audit/events
- admin authentication
- Telegram admin bot
- customer/license lookup
- create license
- extend license
- suspend/revoke license
- activation reset / server move
- expiry notifications
- optional sales/order notifications

The license server keeps all signing secrets and Telegram bot tokens outside GitHub in deployment secrets/environment variables.

## Customer install flow

1. Customer receives a license key.
2. Customer runs the official TwinPanel bootstrap installer.
3. Installer checks OS/resources/ports and creates a machine installation ID.
4. Installer activates the key against the vendor license API.
5. License API returns entitlement/release metadata.
6. Installer obtains the validated TwinPanel release artifact produced from GitHub Actions.
7. Installer installs PostgreSQL + Redis, Backend, Frontend, systemd and Nginx.
8. Database schema is initialized.
9. Admin account is created through a one-time local bootstrap flow.
10. Installer starts services and runs health checks.
11. Installation succeeds only when Web, API, DB and Redis health checks pass.

## Runtime architecture on every customer server

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

Browser requests remain same-origin. Next.js/API runtime targets must point to the API installed on the same TwinPanel deployment by default; no hard-coded dependency on an old Moviline/TwinPanel server is allowed.

## License architecture

Customer panel must contain only the public license client configuration and installation token/state. It must never contain the vendor signing key.

Recommended API contract:

- `POST /v1/license/activate`
- `POST /v1/license/validate`
- `POST /v1/license/deactivate`
- `GET /v1/license/status`
- vendor admin endpoints under `/v1/admin/licenses/*`

Validation response should include at minimum:

- license status
- installation id
- product edition/features
- expiration time
- permitted release channel/version
- signed response or server-verifiable token

A temporary license-server outage should use a bounded grace period rather than instantly stopping customer traffic.

## Telegram license bot

The Telegram bot runs only on the vendor license server and uses the license platform's internal API/database. It is not the sales bot installed for each TwinPanel customer.

Minimum admin actions:

- `/newlicense`
- `/license <key>`
- `/extend <key>`
- `/suspend <key>`
- `/revoke <key>`
- `/resetactivation <key>`
- `/expiring`
- `/stats`

All destructive actions must be restricted to configured Telegram admin IDs and audited.

## Release gates

A commercial release cannot be published unless CI verifies:

1. frontend build
2. backend Python compile/import
3. clean database bootstrap
4. login/bootstrap flow
5. API health
6. frontend-to-API proxy
7. installer shellcheck/syntax
8. install on a clean supported Ubuntu image/VM
9. upgrade from previous release
10. rollback/backup path

## Non-negotiable rule

Do not patch a customer's production backend as a substitute for updating GitHub source. Every production fix must first exist in the product source/release and then be deployed through the update mechanism.
