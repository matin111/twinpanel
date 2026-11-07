# Central Xray bulk bridge (node 13 canary)

This is the **first guarded integration** of the existing central Xray bulk
pilot with the durable node-backfill supervisor. It is **not** a replacement
for the other five protocol-family writers or a proven 1,700-user/3-minute
rollout.

## Lifecycle

1. An admin publishes an Exit to entitled site subscriptions. In the same
   transaction the central queue receives six durable protocol-family jobs.
2. A supervised worker checks load, API readiness, updater state and paid
   account priority; then claims one node/protocol lease.
3. By default **all** families continue through the existing missing-only
   backfill worker.
4. Only when `TWINPANEL_CENTRAL_XRAY_BULK_NODE13=1`, a claimed
   `(node_id=13, protocol=v2ray)` job first invokes
   `twinpanel_xray_bulk_pilot_v1.py --node-id 13 --limit 10 --apply`.
   The pilot uses already-known UUIDs, a validated same-node VLESS profile,
   one remote Xray hot-add batch and one atomic central credential commit.
5. The supervisor counts **only** confirmed `centrally_published` records.
   Invalid output, nonzero exit and timeout fail closed: queue retries, no
   fallback writer competes after an ambiguous live apply. If no central
   records remain to publish, the existing missing-only V2Ray repair path
   handles unsupported or partially provisioned identities.
6. The existing queue lease, retry, status and new-account priority remain
   unchanged. Sing-box, WireGuard, OpenVPN, Cisco and L2TP stay untouched.

## Activation and rollback

Keep the variable **unset** for normal production. After tests and a
separate live canary validate readiness, node #13 operators can explicitly
set `TWINPANEL_CENTRAL_XRAY_BULK_NODE13=1` for the supervised timer
environment (not only an interactive shell). Disable by removing the
variable and restarting only the **backfill worker/timer**, not Xray or
inbounds. Do not delete credentials, reinstall protocols, rotate UUIDs or
clean node configuration as part of this rollout.

## Remaining work before fleet-wide speeds can be claimed

- Load-test batches beyond the existing validated 10-user cap under
  realistic ingress latency while verifying every live user.
- Use node/protocol capability detection and explicit allowlists rather
  than node #13 hardcoding.
- Replace remaining per-user classic drivers with protocol-native atomic
  sync adapters, each with backup, validation and rollback.
- Report full desired/applied/failed counts from central state, and test
  node publication to delivery/subscription reconciliation end-to-end.
- Measure the entire 1,700-user activation on a **new test node**, including
  all entitled protocols, without Xray or tunnel interruptions.
