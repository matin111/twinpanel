# New Exit: install protocols before enrolling existing accounts (16-protocol gate)

## Verified model

TwinPanel's canonical registry has exactly 16 protocols:
- Classic (5): cisco, openvpn, wireguard, l2tp, v2ray
- Modern (11): hysteria2, tuic, anytls, naive, shadowtls, snell,
  mieru, trusttunnel, amneziawg, sudoku, socks5.

The reference Eylan agent implements bulk
`singbox_sync_inbound_users` and `wg1_bulk_sync` operations. Those
informed the desired "provision protocol once, then sync users as a group"
sequence, not copying Eylan's private controller.

## What this draft changes

1. On the **new Exit node** UI, enable standard Classic protocol
   installation and the existing-users checkbox by default. The dedicated
   Xray bootstrap remains the single Xray install path.
2. Do not run the old unbounded per-user network sync during the base
   installation, before modern protocols have been installed.
3. After core install and Xray bootstrap, attempt modern protocols through
   existing adapter-ready bootstrap.
4. Check **all 16** protocol statuses on the same Exit. Do not claim
   successful 16-protocol install or publish the Exit if one is missing.
5. Only after all are online, call the existing set-based, transactional
   publish-and-backfill queue. This does not manually recreate users in the
   FastAPI request.

## Explicit blockers before enabling as the production default

The current catalog still marks **mieru, trusttunnel, amneziawg, sudoku**
as adapter_pending / experimental_pending. They are not installable through
the currently supported automatic Modern installer. The draft therefore
**deliberately blocks publication for a fresh 16-protocol Exit** until
those adapters and node health checks are implemented.

Other incomplete work:
- A durable, restart-resumable **node installation** job (current API uses
  an in-process detached task).
- Native bulk user sync for all Classic/Modern adapters, not just the
  existing bounded Xray pilot and sing-box migration path.
- End-to-end applied count verified on-node and subscription delivery,
  before promising a three-minute or immediate 1700-account rollout.
- Automatic resume/retry when pending protocols become ready.

## Safety

No production server/node, existing credential, UUID, tunnel, SNI,
REALITY profile or endpoint is changed by this draft. Keep it unmerged
until a real integration test can install the full selected 16-protocol
set on a test Exit, bulk-sync eligible users, and verify the result.
