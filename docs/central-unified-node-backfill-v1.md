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

## Unified supervisor default and rollback

The **supervised** `twinpanel-node-auto-backfill` worker now uses the same
active subscription pool for *migrated* and *native* accounts by default.
Eligibility is determined by Subscription + SubscriptionNode +
SubscriptionProtocol, expiration and remaining traffic, not migration origin.
Never change purchased protocol or plan entitlements.

The install/publish API inserts all eligible account memberships atomically
and schedules the seven durable backfill families (five Classic, sing-box and
the bounded four-protocol standalone family) in the same transaction.

Emergency opt-out for the automatic worker only:

```sh
TWINPANEL_UNIFIED_NODE_BACKFILL_V1=0
```

The operator must explicitly choose to deploy/activate the new release.
Existing working user configs are **missing-only**, retaining other nodes'
identity, UUID, secret, inbound, tunnel and SNI. No bulk restart is added to
the Xray path.

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

## Important: 16-protocol queue coverage is not a three-minute bulk guarantee

The unified queue now selects all sixteen protocols via seven families.
The standalone family (Mieru, TrustTunnel, AmneziaWG and Sudoku) is limited
to **three missing node/protocol pairs per cycle**, with the same
subscription-level advisory lock as live account creation, per-node SSH
scoping, missing-only merges, and no new identity rotation.

**Still not production-complete:** Some standalone and Classic drivers
restart a service per account or create one Sudoku service/port per user.
The queue's seven families are not proof of a three-minute bulk install.
A real new-Exit integration canary, rate/CPU tests, quota-agent accounting,
capacity/port scalability and all-node applied-credential verification are
still mandatory. Do not merge/deploy this draft as "instant for all".
The current detached installer can also be interrupted by an API restart.
The durable job tracks stage status but does not yet resume installation.

The admin node overview explicitly reports DISTINCT assigned user owners and
all assigned subscriptions separately; it never uses the legacy agent's
`current_users=0` or claims that an assigned user is online. Usage is
cumulative accepted bytes from the quota ledger. Ports are distinct
configured ONLINE protocol ports, not a full OS socket scan.
