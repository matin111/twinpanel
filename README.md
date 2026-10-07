# TwinPanel 2027

Clean-room Next.js 16 / React 19 UI for TwinPanel. Persian RTL, unified eye-friendly dark mode, one component system, and API contracts matching the audited legacy backend.

## Routes
`/login`, `/admin`, `/admin/users`, `/admin/subscriptions`, `/admin/plans`, `/admin/nodes`, `/admin/tunnels`, `/admin/payments`, `/admin/support`, `/admin/settings`, `/admin/notifications`, `/store`, `/panel`, `/reseller`

## Local
```bash
cp .env.example .env.local
npm ci
npm run build
npm run start
```

## Rules
- Never commit secrets, PKI keys, runtime backups, `.next`, `node_modules`, logs or legacy patch files.
- Frontend/API listen on loopback; Nginx publishes the public domain.
- Backend migration is selective; see `MIGRATION_MANIFEST.md`.
