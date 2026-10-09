# TwinPanel 7-Day Trial License Specification

## Goal

Every new TwinPanel installation may run fully for 7 days before a paid license is required.

## Trial lifecycle

1. Installer generates a stable installation ID / machine fingerprint.
2. Installer calls the vendor license API with `mode=trial` when no paid key is supplied.
3. License server creates at most one trial entitlement for that installation/fingerprint according to policy.
4. Trial starts at first successful activation, not at download time.
5. Trial duration is exactly 7 days.
6. During trial the customer receives normal product updates allowed for the trial channel.
7. Before expiry the panel shows remaining days/hours and purchase/activate actions.
8. A paid license can be entered at any time and upgrades the same installation without reinstalling TwinPanel.
9. After trial expiry the installation enters `trial_expired` state until a paid license is activated.

## Required states

- `trial_active`
- `trial_expiring`
- `trial_expired`
- `licensed`
- `license_expiring`
- `license_expired`
- `suspended`
- `revoked`

## Trial anti-abuse

The license server is authoritative. Deleting local files or reinstalling TwinPanel must not reset the 7-day trial.

The server should persist and compare a privacy-conscious installation fingerprint derived from stable machine attributes. Do not rely on a single mutable value such as hostname.

Recommended policy:

- one active trial per installation fingerprint
- optional additional limits by customer identity / verified Telegram account / email if sales policy requires it
- activation reset only by vendor admin
- all trial creation/reset events audited

## License API contract

### Start or recover trial

`POST /v1/license/trial`

Request should include:

- installation_id
- machine_fingerprint
- product/version

Response should include:

- status: `trial_active` or `trial_expired`
- trial_started_at
- trial_expires_at
- seconds_remaining
- installation_id
- permitted release channel/version
- signed entitlement/token

### Activate paid license

`POST /v1/license/activate`

A paid activation replaces/upgrades the local trial entitlement for the same installation. No reinstall and no data loss.

### Periodic validation

`POST /v1/license/validate`

Returns current authoritative state and expiry. Runtime should cache a signed entitlement and use a bounded grace window for temporary license-server outages.

## Runtime behavior

During `trial_active`, all normal TwinPanel functionality is enabled unless a commercial edition explicitly defines feature limits.

Recommended UX warnings:

- 7-4 days remaining: small trial badge
- 3 days remaining: visible warning
- 24 hours remaining: persistent purchase/activation banner
- expired: admin/control panel remains accessible for license activation, backup/export and diagnostics, but premium management mutations may be blocked according to product policy

Do not abruptly stop existing VPN user traffic merely because the licensing API is temporarily unreachable. License validation must distinguish `server_unreachable` from an authoritative `expired/revoked` response.

## Installer behavior

Installer must support both flows:

- no key supplied -> request 7-day trial
- paid key supplied -> activate paid license immediately

At the end of installation print:

- license/trial state
- expiry timestamp
- remaining duration
- panel URL
- command/path for future license activation or update

## Telegram license bot

Vendor bot must support trial administration in addition to paid licenses:

- `/trial <installation_id>`
- `/trialinfo <installation_id>`
- `/resettrial <installation_id>` (restricted + audited)
- `/expiringtrials`
- `/convert <installation_id> <license_key>`

Normal paid-license commands remain available.

## Commercial conversion

When a customer buys after or during the free week:

1. Vendor issues paid key.
2. Customer enters the key in TwinPanel or installer/license command.
3. Panel calls `/v1/license/activate`.
4. License server binds the paid entitlement to the existing installation.
5. Local state changes from trial to licensed immediately.
6. Existing configuration, users, nodes, tunnels, subscriptions and database remain untouched.

## Source-of-truth rule

Trial enforcement logic belongs to the private vendor license platform. Customer TwinPanel contains only the license client, cached signed entitlement/state, UI and activation workflow. No signing secret or authoritative trial counter is stored in the customer repository/runtime.
