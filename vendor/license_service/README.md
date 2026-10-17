# TwinPanel Vendor License / Distribution Service

این سرویس بخش Vendor-side لایسنس و توزیع TwinPanel است و **نباید داخل بسته مشتری قرار بگیرد**. مسیر `vendor/` با `.gitattributes export-ignore` از Customer Release archive حذف می‌شود.

This service is the vendor-side licensing/distribution control plane and must never ship inside customer release archives.

## Responsibilities

- server-authoritative 7-day trial
- paid license activation
- installation/fingerprint binding
- signed RS256 entitlement tokens
- periodic validation
- suspend/revoke states
- activation limits
- entitled Stable release resolution
- short-lived release download tokens
- append-only operational event records

## Trial policy

- First successful trial activation creates exactly 7 days.
- Trial is keyed by the privacy-preserving machine fingerprint, not only by a local file.
- Reinstalling TwinPanel or deleting local state does not create a new normal trial.
- Trial reset is an explicit vendor-admin action and increments `reset_count`.
- A paid license upgrades the same Installation without touching customer data.

## Required environment

Create `/etc/twinpanel-license-server/license.env` with mode `0600`:

```env
TWINPANEL_LICENSE_DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@127.0.0.1:5432/twinpanel_license
TWINPANEL_LICENSE_PRIVATE_KEY_FILE=/etc/twinpanel-license-server/signing-private.pem
TWINPANEL_LICENSE_PUBLIC_KEY_FILE=/etc/twinpanel-license-server/signing-public.pem
TWINPANEL_LICENSE_PUBLIC_BASE_URL=https://YOUR-LICENSE-DOMAIN
TWINPANEL_LICENSE_RELEASE_ROOT=/srv/twinpanel-releases
TWINPANEL_LICENSE_KEY_PEPPER=LONG_RANDOM_SERVER_ONLY_VALUE
```

`TWINPANEL_LICENSE_KEY_PEPPER` and the signing private key are secrets. Never commit them.

## Signing keys

Generate once on the vendor server:

```bash
install -d -m 700 /etc/twinpanel-license-server
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out /etc/twinpanel-license-server/signing-private.pem
openssl rsa -pubout \
  -in /etc/twinpanel-license-server/signing-private.pem \
  -out /etc/twinpanel-license-server/signing-public.pem
chmod 600 /etc/twinpanel-license-server/signing-private.pem
chmod 644 /etc/twinpanel-license-server/signing-public.pem
```

The public key may be returned to customer installations. The private key must remain only on the vendor host.

## Install service

Recommended dedicated host/user:

```bash
useradd --system --home /var/lib/twinpanel-license-server --shell /usr/sbin/nologin twinlicense || true
install -d -o twinlicense -g twinlicense -m 750 /opt/twinpanel-license-service
install -d -o twinlicense -g twinlicense -m 700 /var/lib/twinpanel-license-server
install -d -o twinlicense -g twinlicense -m 750 /srv/twinpanel-releases
python3 -m venv /opt/twinpanel-license-service/venv
/opt/twinpanel-license-service/venv/bin/pip install -r requirements.txt
```

Use PostgreSQL for production. SQLite is only a safe development fallback.

## Admin CLI

Initialize schema:

```bash
/opt/twinpanel-license-service/venv/bin/python admin_cli.py init-db
```

Issue one-installation 30-day license:

```bash
/opt/twinpanel-license-service/venv/bin/python admin_cli.py issue \
  --customer customer@example.com \
  --days 30 \
  --max-installations 1
```

Issue non-expiring license:

```bash
/opt/twinpanel-license-service/venv/bin/python admin_cli.py issue \
  --customer customer@example.com \
  --days 0
```

Suspend/revoke:

```bash
python admin_cli.py suspended 'TP-...'
python admin_cli.py revoked 'TP-...'
```

Trial reset is explicit and audited:

```bash
python admin_cli.py reset-trial <64-char-fingerprint> --reason 'support approved reset'
```

## Publish a release

The release package is produced from the canonical `release/stable-v1` branch after CI and clean-install/upgrade validation.

```bash
python admin_cli.py publish-release \
  --version 1.1.0 \
  --channel stable \
  --file /secure/incoming/twinpanel-1.1.0.tar.gz \
  --installable \
  --notes-fa 'نسخه پایدار 1.1.0' \
  --notes-en 'Stable release 1.1.0'
```

The CLI copies the package to the release store, calculates SHA256 and writes `/srv/twinpanel-releases/stable.json`.

## Public bootstrap activation

Only after the Vendor API is deployed and tested:

1. set `TWINPANEL_LICENSE_PUBLIC_BASE_URL` to the final HTTPS domain;
2. verify `/health` and `/v1/releases/latest`;
3. publish an installable release;
4. set `license_api_url` in public `matin111/tp27-core/twinpanel/config.json`;
5. change public config `enabled` to `true`;
6. update `tp27-core/twinpanel/releases/stable.json` to the same validated version with `installable:true`.

The customer then needs only:

```bash
curl -fsSL https://raw.githubusercontent.com/matin111/tp27-core/main/twinpanel/install.sh | sudo bash
```

## Reverse proxy

Expose only HTTPS publicly. Nginx/Caddy should proxy to `127.0.0.1:8110`, enforce request size limits, rate limit activation/validation endpoints, and keep access logs free of license keys and entitlement tokens.

## Important security rules

- never log raw License Keys;
- never put signing private key in GitHub;
- never expose the private TwinPanel repository to customer installers;
- keep release URLs short-lived;
- verify SHA256 client-side before extraction;
- back up the license database and signing key separately;
- use PostgreSQL backups and append-only external audit retention for production;
- license-server outage is different from authoritative expiry/revocation; existing VPN traffic must not be abruptly killed on temporary network failure.
