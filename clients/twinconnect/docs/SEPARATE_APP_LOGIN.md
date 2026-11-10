# TwinConnect — separate app username, password and subscription link

Status: backend/frontend implementation in an unmerged branch. Do not deploy until tests, auth review and integration dependencies pass.

For every **app-entitled** subscription created via the central subscription factory, the panel issues a *separate* app username and random 160-bit app password. The VPN username, VPN password, protocol credentials, server IP/port/SNI and original subscription share URL remain unchanged.

App usernames use a unique panel namespace and owner prefix:
- Owner: `TP<16HEX>_A_APP<16HEX>`
- Reseller: `TP<16HEX>_R<RESID>_APP<16HEX>`

No account or app credentials are created when a license does not include the app. Existing subscriptions can be issued app credentials lazily, by authenticated admin/reseller delivery or a verified owner's Telegram delivery route, without changing VPN credentials. Issuance is idempotent; **only the explicit reset action changes the app password**.

## Customer delivery

Three separate, copyable fields:
- App username
- App password
- Subscription link

The reseller Telegram verified purchase/order-delivery message includes app credentials under its own heading, separate from the VPN login. The existing bot «دریافت لینک اکانت» / account-link lookup remains username-only and never requires or issues TwinConnect app credentials. No app secret is embedded in the subscription URL or QR. The existing share URL stays stable after password resets.

## API (owning panel, never the vendor registry)

- `POST /v1/central-app/public/login`: `{"username":"...","password":"..."}`. Checks the app-only hash, lockout (five failed attempts, 15 minutes), subscription/license/owner status and returns a short-lived app-only JWT (30 minutes) with verified tenant branding. The vendor registry receives only the namespace.
- `GET /v1/central-app/session/brand`: authenticated session.
- `GET /v1/central-app/session/protocols`: authenticated session.
- `POST /v1/central-app/session/profiles`: authenticated session + selected protocol only; native OS-engine readiness remains a *separate* client-side requirement.
- `POST /v1/central-app/admin/subscriptions/{id}/app-delivery`, `/app-password-reset`: admin-only issue/view/reset.
- `POST /v1/central-app/reseller/subscriptions/{id}/app-delivery`, `/app-password-reset`: strictly linked reseller-only issue/view/reset.

App password rotation increments the credential revision to revoke previous app JWTs, but does not change the subscription URL or VPN/protocol passwords.

## Security

App passwords are salted+hashed for authentication and separately encrypted for authorized re-delivery (purpose-separated Fernet key derived from the panel secret); they are never stored as plaintext in the database. HTTPS + no-store/private + no-referrer for credential responses. Do not log app passwords, JWTs, subscriptions, or sensitive profiles. **The encryption key must remain persistent across backup and restore** to preserve redelivery; otherwise use authenticated app-password reset.

The Flutter login now contains only username, password and a short single-line guide. It does not request VPN credentials, subscription URLs, panel codes or a demo account. It discovers the licensed panel by the namespace in the app username, posts credentials only to the correct panel, and uses the short-lived app session to fetch brand/protocol data. The existing VPN-native connection gate stays disabled unless actual engine capabilities pass.

## Rollout

1. Merge/ship vendor panel directory/entitlement dependencies and previous API/theme PRs in dependency order.
2. Validate additive `subscription_app_credentials` schema creation (no existing subscription columns rewritten).
3. Validate owner/reseller bot delivery, stable links, password reset, and login from Windows test app on a **non-production** licensed panel.
4. Add and verify transport-level protections/rate limiting and monitoring before broad public release.
5. Deploy backend and client together. Do not enable on panel-only licenses.
