# ShadowTLS identity-preserving rollout (staged; **not active by default**)

Legacy ShadowTLS v3 in TwinPanel terminates in a single shared
`aes-256-gcm` Shadowsocks listener. Native sing-box telemetry reports an
empty username for its internal flows. It is not possible to attribute
the resulting bytes or sessions to individual subscriptions reliably.

## New guarded implementation

- Parallel ShadowTLS v3 ingress (new, non-conflicting port) and
  `2022-blake3-aes-128-gcm` multi-user Shadowsocks inner.
- Authenticated inner users preserve the actual legacy username, including
  migrated accounts that do **not** use `tp-sub-N`.
- Per-user 128-bit Shadowsocks keys derived with HMAC-SHA256 from a private
  random 256-bit node-only derivation seed, the actual legacy user name and
  outer password. The private seed is **never included in a delivered client
  profile**. This avoids reducing inner-key security to a short historic
  outer password.
- Add/revoke paths synchronize both identity listeners only **if the parallel
  listener already exists**. Legacy-only nodes are unchanged.
- Client delivery remains legacy unless the operator explicitly marks
  `shadowtls_identity2022.delivery_enabled=true` **after** routing and
  end-to-end tests. The delivered profile contains only that subscriber's
  authenticated inner credential.
- Canonical quota, usage and selective close accept only native connection
  events from `twinpanel-shadowtls-identity-inner` where sing-box reports
  the authenticated user name. Existing shared
  `twinpanel-shadowtls-inner` traffic is not billed or counted.

## Non-destructive rollout prerequisites

1. Back up node state and config, and map all node usernames to real active
   subscriptions. Resolve unmatched legacy identities instead of guessing
   from IP addresses. Fail closed for unknown users.
2. Reserve a unique free TCP port **and** arrange public or tunnel forwarding.
   Port `18448` is a preflight example, not a universal production default.
3. Generate two independent random secrets for each node: a 16-byte base64
   Shadowsocks 2022 server key, and a 32-byte base64 **private derivation**
   seed. Persist both securely and atomically in node state/parallel config.
   The pure `stage_parallel_identity_inbounds` function does not write either.
4. Validate the generated config with the installed sing-box binary, test
   authenticated connectivity for at least two distinct users, wrong-user
   rejection, node/tunnel reachability, and account add/revoke idempotence.
5. Install and validate the parallel listener without replacing the legacy
   listener. Verify online, real nonzero cumulative bytes, historical baseline,
   expiry, quota exhaustion, and cross-protocol concurrent-session enforcement
   against the canonical database. Roll back on anomalies.
6. Explicitly enable modern client delivery only for verified nodes. Keep old
   customer configs functioning during the migration window; do not remove
   legacy ShadowTLS until users have updated or the operator approves a
   deprecation window.

**Safety:** Do not activate a port, restart production sing-box, rotate an
existing credential, synthesize a session or apply historical aggregate bytes
solely because these migration primitives are installed. The code is staged
for a coordinated opt-in rollout; adding it to a TwinPanel release does not
by itself solve legacy ShadowTLS accounting.
