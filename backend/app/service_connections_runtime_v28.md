# Service Connections Runtime V28

This marker documents the release-line regression fixed by V28.

The admin UI kept calling `/v1/tunnels/{id}/service-connections` and its repair/reconciliation actions after the backend runtime registrations from the previously merged V31/V36/V37 work disappeared from the public release lineage.

V28 restores those routes on the current self-hosted runtime, keeps Xray reconciliation UUID-preserving, and makes TP2027 real-egress repair non-destructive to a healthy SSH Relay/SSH TUN/Backhaul/MTunnel fallback when no TP2027 member verifies.
