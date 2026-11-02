# TwinPanel Trial Account V1

Trial accounts are a TwinPanel subscription feature, not a license feature.

- Trial policy is stored per sales Plan.
- Default trial values are 1 day and 500 MB.
- A durable `trial_claims` ledger enforces one trial per canonical `User.id` across customer panel and Telegram entry points.
- Trial subscriptions snapshot the selected Plan protocols and Exit nodes and use the same centralized 15-protocol account provisioner as paid subscriptions.
- Main Telegram bot calls `/v1/trial/claim` with the linked customer session.
- Reseller Telegram bot resolves its linked TwinPanel user and calls the same `claim_trial_for_user` service; its zero-cost subscription is linked into `ResellerSubscription`.
- A claimed trial remains claimed even if its Subscription is later deleted or expires.
