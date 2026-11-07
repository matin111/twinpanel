# Central unified active-account backfill — guarded rollout V1

## Target

Adding a new Exit must select **all eligible active subscriptions**,
including imported Eylan/Sanaei/Marzban/Pasargad subscriptions AND accounts
created inside TwinPanel or its bots. The source of truth is
`Subscription` + `SubscriptionNode` + `SubscriptionProtocol`,
not whether a migration marker exists.

The existing set-based publisher already creates node memberships for both
classes atomically. This patch adds one shared account selection for the
background **sing-box (7 protocols) + five Classic** families.

## Safety / default behavior

**Disabled by default.** The existing background timer only includes both
classes when this server-local flag is explicitly set:

```sh
TWINPANEL_UNIFIED_NODE_BACKFILL_V1=1
```

This changes only the missing-node selection of the existing durable
one-family-at-a-time backfill queue, not its SSH update strategy or online
customer account creation. Rolling back: unset the flag and restart only the
backfill timer environment.

Manual migration script stays imported-only by default. Targeted canary
through the existing CLI can explicitly use:

```sh
python backend/scripts/twinpanel_existing_node_backfill_v1.py \
  --node-id <EXISTING_TEST_EXIT_ID> --protocol singbox \
  --include-all-active
```

Without `--apply --confirm-node-id <same node id>`, this is read-only.
The exact node must already be healthy, visible and configured; tests use
only simulated database records, never a real server.

The selected subscription must be ACTIVE, not past expires_at, not exhausted
and already entitled to the selected protocol and Exit. The writers skip
pairs that already have a config for that node, reuse existing secrets,
preserve other nodes' items, and do not rewrite UUIDs. Paid new-account
orders retain safety priority.

## Not yet complete: 16-protocol native bulk

The queue currently has 6 families covering 5 Classic plus 7 sing-box
protocols. **Mieru, TrustTunnel, AmneziaWG, Sudoku** use separate standalone
drivers and are not part of this worker yet. Some classic and standalone
drivers still provision per user and may restart services per user. Therefore
this patch **does not** meet the target of adding ~1,700 accounts across all
16 protocols in ~3 minutes, and must not be presented as full rollout.

Before production activation: integrate the standalone adapters into a
bounded, replay-safe batch executor, establish lock coordination with the
new-account fast provisioner, verify exact per-node applied identities,
and run a real new-Exit canary including an imported and native account.
