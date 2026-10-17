# TwinPanel License Service Contract

This document defines the vendor-side license/distribution API consumed by customer installations. The vendor signing key and authoritative trial/license database never ship with TwinPanel customer installations.

## Identity

Every installation has:

- `installation_id`: random UUID generated once during first install
- `machine_fingerprint`: SHA-256 of stable machine attributes (for example `/etc/machine-id` + DMI product UUID after normalization)
- `product`: `twinpanel`
- `installed_version`
- `release_channel`

Raw hardware identifiers should not be logged when a privacy-preserving hash is sufficient.

## Local state

Customer server path:

```text
/var/lib/twinpanel-license/state.json
```

Mode: `0600`.

Contains only client-side state such as:

- installation_id
- machine_fingerprint hash
- entitlement token / signed lease
- license state
- expires_at
- last_validated_at
- offline_grace_until
- entitled channel/version

It must never contain the vendor signing private key.

## Vendor database

Minimum entities:

### installations

- id
- installation_id (unique)
- fingerprint_hash
- first_seen_at
- last_seen_at
- current_version
- release_channel
- status

### trials

- id
- installation_id
- started_at
- expires_at
- status
- reset_count
- reset_reason

A fingerprint/installation may receive only one normal trial unless a vendor admin performs an audited reset.

### licenses

- id
- license_key_hash
- customer_ref
- edition
- status
- starts_at
- expires_at
- max_installations

### activations

- id
- license_id
- installation_id
- activated_at
- deactivated_at
- last_validated_at

### license_events

Append-only audit events for create, activate, validate, extend, suspend, revoke, trial reset, activation reset, and update entitlement decisions.

## API

### `POST /v1/install/resolve`

Used by the public bootstrap installer.

Request:

```json
{
  "product": "twinpanel",
  "installation_id": "uuid",
  "machine_fingerprint": "sha256",
  "license_key": null,
  "requested_channel": "stable",
  "updater_version": 1
}
```

If `license_key` is null/empty, the server starts or recovers the 7-day trial.

Response:

```json
{
  "ok": true,
  "license_state": "trial_active",
  "trial_expires_at": "2026-10-24T12:00:00Z",
  "seconds_remaining": 604800,
  "version": "1.1.0",
  "channel": "stable",
  "download_url": "https://signed-download.example/...",
  "sha256": "...",
  "entitlement_token": "signed-token",
  "download_expires_at": "2026-10-17T12:15:00Z"
}
```

The download URL must be short-lived. The installer must verify SHA256 before extraction.

### `POST /v1/license/trial`

Start or recover trial for an existing installation.

### `POST /v1/license/activate`

Activate a paid key on the existing installation without reinstalling.

### `POST /v1/license/validate`

Validate the cached entitlement. Returns authoritative state, expiry, permitted release channel, and latest entitled version.

### `GET /v1/releases/latest`

May expose non-sensitive release metadata. Actual package download still requires entitlement.

### `POST /v1/releases/resolve-download`

Returns an expiring signed package URL plus SHA256 for the latest entitled release.

## Trial timing

The trial starts at the first successful server-side activation, never at download time.

Exactly seven days are granted:

```text
trial_expires_at = trial_started_at + 7 days
```

Recommended client warnings:

- more than 3 days: small badge
- 3 days or less: warning notification
- 24 hours or less: persistent warning banner
- expired: clear activation-required state

## Expiry behavior

After an authoritative `trial_expired`, `license_expired`, `suspended`, or `revoked` response:

Allowed:

- admin login
- license activation/validation
- backup/export
- diagnostics/health
- viewing installed version/update eligibility

Restricted:

- creating/renewing subscriptions
- provisioning nodes
- creating/repairing tunnels
- changing commercial plans/payments
- reseller sales/management mutations
- other premium management mutations

Existing VPN data-plane sessions should not be abruptly killed by a temporary license-server outage. A short offline grace window applies only after a previously valid signed entitlement and only when the server is unreachable. It does not override an authoritative revoked/expired state.

Recommended offline grace: 24 hours.

## Update entitlement

The license service is the source of truth for which release a customer may download. The customer panel never embeds a GitHub access token and never performs `git pull` against the private product repository.

Update flow:

1. panel validates entitlement
2. panel learns newest entitled version
3. admin presses Update
4. updater asks license service for a short-lived package URL
5. package is verified and installed into a new release directory
6. health check passes or automatic rollback occurs

## Security

- Store only hashes of license keys where possible.
- Use rate limits on activation/validation endpoints.
- Sign entitlement responses/tokens with a vendor-held key.
- Keep signing private keys outside GitHub and outside customer servers.
- Audit every destructive vendor-admin action.
- Do not trust client-provided trial dates or remaining time.
