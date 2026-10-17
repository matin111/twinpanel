# TwinPanel Vendor License Platform V1

> This directory/branch is vendor-side infrastructure. It must **not** be included in customer TwinPanel release archives.

## Responsibilities

- one seven-day trial per machine fingerprint
- paid license issue/activate/extend/suspend/revoke
- activation reset for approved server moves
- signed RS256 entitlement issuance/validation
- install resolver for the public one-line bootstrap
- entitled release resolution and short-lived download tokens
- private release package delivery with SHA256
- audit-ready installation/license/release records

## Required environment

All variables use the `TPLIC_` prefix:

```text
TPLIC_DATABASE_URL=postgresql+psycopg2://twinpanel_license:...@127.0.0.1:5432/twinpanel_license
TPLIC_ADMIN_TOKEN=<random 64+ chars>
TPLIC_LICENSE_KEY_PEPPER=<random 64+ chars>
TPLIC_SIGNING_PRIVATE_KEY_FILE=/etc/twinpanel-license/private.pem
TPLIC_SIGNING_PUBLIC_KEY_FILE=/etc/twinpanel-license/public.pem
TPLIC_PUBLIC_BASE_URL=https://license.example.com
TPLIC_RELEASE_ROOT=/var/lib/twinpanel-license/releases
TPLIC_TRIAL_DAYS=7
TPLIC_ENTITLEMENT_TTL_SECONDS=172800
TPLIC_DOWNLOAD_TOKEN_TTL_SECONDS=900
TPLIC_DEFAULT_RELEASE_CHANNEL=stable
```

The RSA **private** key exists only on this vendor server. Customer servers receive only the public key.

## API contract

Customer/public endpoints:

```text
POST /v1/install/resolve
POST /v1/license/trial
POST /v1/license/activate
POST /v1/license/validate
POST /v1/license/release
GET  /v1/release/download/{version}?token=...
```

Vendor-only endpoints require `X-Admin-Token`:

```text
POST /v1/vendor/licenses
GET  /v1/vendor/licenses
POST /v1/vendor/licenses/{id}/extend
POST /v1/vendor/licenses/{id}/suspend
POST /v1/vendor/licenses/{id}/activate
POST /v1/vendor/licenses/{id}/revoke
POST /v1/vendor/licenses/{id}/reset-activation
POST /v1/vendor/trials/reset
POST /v1/vendor/releases
GET  /v1/vendor/releases
PUT  /v1/vendor/releases/{id}/installable
GET  /v1/vendor/installations
```

## Trial behavior

The first successful trial request creates a `TrialIdentity` keyed by a server-side hash of the machine fingerprint. Reinstalling TwinPanel may generate a new installation ID, but the same fingerprint recovers the original trial start/expiry instead of creating another seven days.

Trial states:

- `trial_active`
- `trial_expiring` (3 days or less)
- `trial_expired`

After expiry the customer panel keeps admin login, license activation, backup/export and read-only diagnostics available. Existing VPN data-plane traffic is not abruptly terminated; protected new management mutations are blocked by the customer-side license guard.

## Paid license behavior

A generated raw key is returned once. The database stores only a peppered SHA256 hash plus a display prefix/last4. By default a paid license binds to one machine fingerprint. Reinstall on the same machine remains valid; moving to a different machine requires the vendor `reset-activation` action.

## Release publishing

1. Build a release archive from validated `release/stable-v1` source only.
2. Copy the archive into `TPLIC_RELEASE_ROOT`.
3. Calculate SHA256.
4. Register it with `POST /v1/vendor/releases` and `installable=false`.
5. Complete clean-install + upgrade + rollback tests.
6. Switch `installable=true` only after all release gates pass.
7. Update the public `tp27-core/twinpanel/releases/stable.json` version/notes.

The download URL returned to customers contains a short-lived signed release-download token. No GitHub private-repository token is shipped to the customer.

## Key generation

```bash
install -d -m 700 /etc/twinpanel-license
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out /etc/twinpanel-license/private.pem
openssl rsa -pubout -in /etc/twinpanel-license/private.pem -out /etc/twinpanel-license/public.pem
chmod 600 /etc/twinpanel-license/private.pem
chmod 644 /etc/twinpanel-license/public.pem
```

Back up the signing private key securely/offline. Losing it prevents future entitlement signing; exposing it requires immediate rotation and entitlement migration.
