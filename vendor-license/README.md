# TwinPanel Vendor License Center

This service is the **vendor-side** license issuer for TwinPanel. It is not part of the customer runtime and must be deployed only on infrastructure controlled by the TwinPanel vendor.

## Security boundary

- Keep `VENDOR_LICENSE_PRIVATE_KEY_FILE` only on the vendor server.
- Customer servers receive only the public verification key.
- The Iran mirror must never receive the private signing key.
- Use a long random `VENDOR_LICENSE_ADMIN_TOKEN` and restrict the admin API by firewall/reverse proxy.

## Customer API

The service implements the contract used by TwinPanel clients:

- `POST /v1/license/activate`
- `POST /v1/license/validate`
- `POST /v1/license/trial`

## Admin API

Admin endpoints require `Authorization: Bearer <VENDOR_LICENSE_ADMIN_TOKEN>`.

- `GET /v1/admin/plans`
- `POST /v1/admin/plans`
- `GET /v1/admin/licenses`
- `POST /v1/admin/licenses/manual`
- `POST /v1/admin/licenses/{id}/renew`
- `POST /v1/admin/licenses/{id}/status`

A manual license can be created from a plan or as a custom license with its own duration, features, server IP and Installation ID.

## Plan fields

Each plan supports duration, price, max nodes, max resellers, edition, release channel and feature flags. The first version stores these limits in the vendor database; the signed entitlement includes edition/features and can be extended with hard limits in the next iteration.

## Run

```bash
cd vendor-license
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export VENDOR_LICENSE_ADMIN_TOKEN='...'
export VENDOR_LICENSE_PRIVATE_KEY_FILE='/etc/twinpanel-vendor/license-private.pem'
uvicorn app:app --host 127.0.0.1 --port 8095
```

Put Nginx/Caddy in front with TLS. For production, set `VENDOR_LICENSE_DATABASE_URL` to the vendor PostgreSQL database instead of SQLite.
