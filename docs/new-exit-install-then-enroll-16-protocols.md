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

## Status and remaining blockers before merging

All 16 protocol names are present in the canonical account registry. Four
standalone adapters (Mieru, TrustTunnel, AmneziaWG, Sudoku) are activated at
runtime by `standalone_protocol_runtime`; their static catalog initially
shows pending because that import applies runtime overrides. The modern
bootstrap now explicitly activates these adapters and can use each catalog's
recommended defaults when there is no healthy source node.

The draft also:
- Keeps newly staged Exit nodes hidden until publication.
- Defers the legacy per-user subscription loop for Exit only; leaves Iran
  relay behavior unchanged.
- Persists effective ports after runtime conflict remapping.
- Requires a new read-only SSH/service/listener health audit of all sixteen
  protocols before marking the node desired for eligible users.

**Still not complete:** The current automatic enrollment queue has only six
worker families and some account writers still operate per user. The 16
protocol services becoming healthy is a separate milestone from having all
active users applied at the node. We must not report 1,700 accounts "active"
or `3 minutes` based only on membership rows or queued work.

The new-node background installer itself is still an in-process FastAPI task.
A process restart can interrupt setup; the proper future fix is a durable,
restart-resumable installer with persisted stage and safe credential handling.

End-to-end acceptance must measure:
1. A completely new Exit (including standalone protocols) is installed.
2. Exactly the expected *eligible* old subscriptions and their purchased
   protocol permissions are enrolled, without UUID/password rotation.
3. Each new-node live protocol has all its intended users, not just SQL
   membership. The last verification includes multiple account clients.
4. The app and existing Exit nodes stay online through failure/retry.
5. Restart during install/backfill resumes without duplicating accounts.

Do not merge or deploy this draft to production before that integration
testing and the remaining bulk adapters are complete.

## Safety

No production server/node, existing credential, UUID, tunnel, SNI,
REALITY profile or endpoint is changed by this draft. Keep it unmerged
until a real integration test can install the full selected 16-protocol
set on a test Exit, bulk-sync eligible users, and verify the result.
