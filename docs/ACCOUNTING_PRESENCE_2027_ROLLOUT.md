# TwinPanel accounting and presence modernization (staged)

## Verified production findings (RC.715, 2026-11-08)
- QuotaSession is canonical for observed sessions; QuotaUsageEvent is an append-only usage ledger; QuotaCursor tracks cumulative source counters.
- Admin subscription status and public Connect status use a 180-second recent-activity threshold; the admin UI polls at 15 seconds and replaces previous status after a successful response.
- `quota_usage_events` has 660k+ rows; existing `ix_quota_usage_subscription_created` does not index `reported_at` used in recent-presence queries.
- Fast presence and heavy quota reconciliation share parts of SQLAlchemy accounting paths; a slow collector may result in stale `last_seen_at` even while the data plane remains connected.
- First-use activation sets `starts_at`/`expires_at` in `open_session`. Usage is charged by canonical cumulative-counter logic. These are financial/contractual invariants: do not change casually.

## Architecture to implement, behind feature flags
1. **Separate observation from billing:** protocol adapters report authenticated session-open/heartbeat/close observations into a bounded queue. Never infer real socket state from ping or stale traffic. Append-only quota events are processed by one billing writer per (node, protocol, identity, epoch). Observations must not carry credentials to the UI.
2. **Idempotent usage:** durable unique `event_id` and `(node_id, source_key)` cursor, monotonic sequence and counter epoch. Same observation replayed twice must be charged once; counter reset starts a fresh epoch without negative charge; quarantine identity conflicts instead of rewriting historical owners.
3. **Subscription time:** server-authoritative UTC, immutable first activation timestamp, expiry computed once in the same transaction under a subscription row lock. Never extend expiry from heartbeat or reconnect. Respect unlimited-duration and exhausted-volume semantics.
4. **Presence is tri-state:** ONLINE on fresh authoritative observation, OFFLINE on authoritative close or healthy fresh sweep that confirms absence, UNKNOWN/STALE when the collector is late, errored, or node unreachable. Do not turn telemetry outage into a fabricated disconnect. Store last successful sweep and lag per node/protocol.
5. **Read model:** lightweight aggregated per-subscription presence projection (or Redis cache with TTL and DB fallback) updated from committed observations; the dashboard/API must not scan the entire historical usage ledger every 15s.
6. **Isolation/backpressure:** dedicated bounded worker per protocol/node group; bulk provisioning has lower priority than connection observations. Use batch writes, savepoints for corrupt identities, bounded SQL lock timeouts and jittered retry.
7. **Visibility:** collector lag p50/p95, fresh-observation ratio, lock waits, queue backlog, accepted/rejected usage, user-identity conflicts, repeated event rates, and difference between admin and Connect API.

## Safe deployment gates
- Snapshot backup verified complete BEFORE changing PostgreSQL.
- Phase A: add `20261108_live_activity_index.sql` with CONCURRENTLY. Check valid index and use EXPLAIN (ANALYZE, BUFFERS) for queries with `reported_at >= cutoff AND accepted_bytes > 0`. No data-plane restart.
- Phase B: ship tri-state API as additive fields; existing boolean is preserved until both UI and public Connect clients support UNKNOWN.
- Phase C: shadow-read the new presence projection against current endpoint without affecting billing; canary one node, then compare 24-hour convergence metrics.
- Phase D: switch read path by feature flag; never change billing writer or subscription activation simultaneously with presence.
- Rollback switches read model back; no deletion of session, cursor, usage, expiry or source events.

## Regression gates
- Duplicate cumulative observation: zero additional charge.
- Counter restart/wrap/reorder: no negative or duplicated usage.
- Two simultaneous connections: correct device limit; no duplicate first activation.
- First connection, reconnect, renew and unlimited duration: correct starts/expires in UTC.
- Expired/exhausted subscription: cannot be admitted even if telemetry reports an existing socket.
- Node/collector outage: UNKNOWN; never falsely claim OFFLINE or ONLINE.
- API/DB query failure: preserve last confirmed display with stale indication, never blank all users.
- Admin/public Connect projections agree for the same timestamp/protocol.
- Performance under 2k subscriptions and 600k+ historical usage events: test p95 before production rollout.
