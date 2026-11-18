# TwinConnect Iran Bootstrap (control-plane only)

## User problem
When Iranian ISPs restrict access to international IPs/DNS, a first-time app
login cannot resolve the vendor directory, retrieve the tenant panel, fetch the
subscription-scoped server inventory or download its authenticated profiles.

**This is not a VPN tunnel or a promise of connectivity in total isolation.**

## Current implementation
The Flutter client calls the real `/v1/app/resolve/{namespace}`,
`/v1/central-app/public/login`, and authenticated
`/v1/central-app/session/{servers,protocols,profiles,account,refresh}`
endpoints using the usual HTTPS hostname.

After network/DNS/TLS transport errors, it tries a **domestic TCP endpoint**
at `94.183.231.158:80` using HTTP CONNECT restricted to
`panel.matindnspro.sbs:443`. The HTTPS hostname, SNI, certificate chain,
hostname validation and bearer authentication are unchanged: TCP is re-routed,
HTTPS is **not** disabled.

A secondary TLS-SNI passthrough implementation for :443 exists but is **not**
enabled on the live Iran :443 VPN multiplexer. It must be integrated into the
existing allowlist without dropping customer VPN sessions.

A successful domestic connection is preferred for 10 minutes so subsequent
server and profile requests do not wait repeatedly for failed international
DNS. A meaningful 401, 403, 429, invalid plan or revoked session is never
converted to a successful login or skipped.

## Server
`connect_proxy.py` runs with systemd on Iran :80, forwards the opaque
CONNECT stream to the pinned France control-plane IP, and rejects all
non-allowlisted targets (including CONNECT to other ports). It does not
terminate TLS or store user credentials. The service is independent of
existing VPN/TwinTunnel port 443 services.

On the IR node (from a reviewed checkout of this directory):

```bash
sudo bash ./install.sh
systemctl status twinconnect-iran-bootstrap-connect
```

Test with a public, unauthenticated health endpoint without disabling TLS
certificate verification:

```bash
curl --noproxy '' --proxy http://94.183.231.158:80 \
  https://panel.matindnspro.sbs/health
```

Rollback of **only** the control-plane relay, leaving VPN services untouched:

```bash
sudo systemctl disable --now twinconnect-iran-bootstrap-connect
```

## Tested
- Authenticated TLS certificate validation through Iran loopback CONNECT
  and from the France server to Iran public IP
- Public directory HTTP 200 through domestic relay
- Protected subscription inventory returns HTTP 401 with no credentials
- Unsupported proxy targets are rejected
- Python synthetic proxy and SNI forwarding tests
- Flutter transport-scoping unit tests

## Real-world limits and remaining tasks
1. Under a *complete* international shutdown, the Iran node must still have
   one working uplink to France (or a separate authenticated domestic replica).
   Without an uplink, live credentials and newly issued private profiles cannot
   be retrieved by this simple relay.
2. Port-80 CONNECT may itself be filtered by some Iranian mobile providers.
   Test on representative mobile and wired providers; consider a separate
   TLS-protected domestic control endpoint with distinct reachable IPs.
3. Independent Iranian-hosted, signed/encrypted short-lived profile snapshots
   are a separate feature requiring explicit security, revocation and backup
   design. They are not present.
4. The PR branch is an experimental app build. It does not automatically update
   customers' already-installed Windows/Android apps. Run device tests and
   ship a new signed app release after CI passes.
