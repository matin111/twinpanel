# Subscription creation provisioning contract

A subscription create request is successful only after every explicitly selected protocol has an active generated `ProtocolCredential` with deliverable config and quota synchronization succeeds.

If provisioning is partial or quota synchronization fails, creation must fail closed: the subscription is not left ACTIVE and cleanup/revoke is queued for reconciliation.
