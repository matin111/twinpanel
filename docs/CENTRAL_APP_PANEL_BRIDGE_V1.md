# Central app bridge — TwinPanel installation (draft)

This is an additive integration layer for the vendor-side `feat/central-app-directory-v1` directory. It does **not** replace the existing Connection page, VPN protocol engines or subscription API.

## 1. Identity and prefixes

The stable tenant namespace is:

```
"TP" + upper(sha256("twinpanel:central-app:v1:" + installation_id)[:16 hex])
```

A reseller prefix is derived from its **immutable database ID**, not its mutable reseller code:

```
TP<16-HEX>_R<reseller-id-in-hex>_
```

When the vendor-signed local license includes `central_app` and is valid, newly created reseller subscriptions automatically receive this prefix in the common account factory. The same function is called from:
- normal reseller sale
- compatibility reseller sale / legacy bot
- direct manual reseller sale
- owned-plan reseller sale / owned bot.

Existing usernames, credentials, subscription links, quotas, traffic, nodes and active VPN sessions are never renamed or migrated by this feature. Panel-only licenses keep their current username formatting. A duplicate/prefix from another reseller is rejected. Names generated through this path are kept at or below 64 ASCII characters for classic protocol compatibility.

## 2. Admin and reseller settings

Additional table `central_app_contacts` (created by existing `Base.metadata.create_all`):
- `reseller_id=0` for panel owner
- `reseller_id=<reseller.id>` for a reseller
- logo, primary/secondary colors, Telegram support, renewal URL, phone and website.

Existing branding tables and profiles are not changed.

Protected routes:
- `GET /v1/central-app/admin/info`: tenant namespace, app license state
- `POST /v1/central-app/admin/register`: server-to-server registry enrollment (requires app license and panel-admin session)
- `GET/PUT /v1/central-app/admin/profile`: owner contact overlay
- `GET/PUT /v1/central-app/admin/resellers/{id}/profile`: edit named reseller overlay
- `GET/PUT /v1/central-app/reseller/profile`: authenticated reseller's own contact and immutable prefix.

Public route:
- `GET /v1/central-app/public/brand/{share_token}`: resolves existing subscription token, **then** uses `ResellerSubscription` ownership to return that reseller's brand/contact, or panel-owner brand when no reseller link exists. A customer never receives another reseller's contact due to a username prefix guess.

## 3. Limitations before production

- Vendor-side registration of public panel URL requires a signed app entitlement and should gain proof of hostname ownership plus rate limits before broad rollout.
- The client VPN engines and Flutter binaries are not in this PR.
- Username-only sign-in needs subscription-specific authentication; prefix alone only routes traffic to the correct installation and **does not authorize anyone**.
- The current public brand route reuses the Connection page's share-token validation, including its existing expiry rules. Expired subscriptions may require a separate limited, renewal-only brand lookup.
- Deployment requires both vendor entitlement/directory changes and this panel branch to be reviewed and tested. Never deploy only half the contract.
- No production server update, changes to active subscriptions or new VPN installation logic is included.

## Deployment check

Run GitHub workflow `Central App Tenant Identity V1`, inspect migrations creating `central_app_contacts`, and smoke-test both a panel-only install and an app-enabled install before merging. Test original admin subscriptions, reseller sales, bot sales, existing share links, and license revocation.
