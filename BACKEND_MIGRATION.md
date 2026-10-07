# TwinPanel Backend Migration

## Source

Legacy production backend:

`/root/vpnshop/vpnshop`

## Clean export

`twinpanel-backend-clean-20261007-191535.tar.gz`

SHA256:

`7456359ddf54f7e5f3c67400757a98fbaa26bb138fe175f273b90c9355c89b11`

## Migration branch

`migration/backend-clean-20261007-191535`

## Imported

- backend/app
- backend/requirements.txt
- backend/alembic.ini when present
- backend/alembic when present
- quota-agent source when present

## Explicitly excluded

- .env
- passwords and runtime secrets
- private keys
- certificates
- PKI
- SQL/database dumps
- SQLite databases
- logs
- caches
- __pycache__
- historical backup files
- candidate files
- old/broken/disabled versions

## Rule

This branch is an isolated migration branch.
Production and preview runtime must not use it until validation is complete.
