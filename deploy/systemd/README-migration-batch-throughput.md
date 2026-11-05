# High-throughput migration (16-core production profile)

Two `.conf` files in this directory are tested systemd drop-ins for `twinpanel-migration-batch.service` and `twinpanel-migration-batch.timer`. Install as `/etc/systemd/system/twinpanel-migration-batch.service.d/30-safe-load.conf` and `/etc/systemd/system/twinpanel-migration-batch.timer.d/30-safe-load.conf`; run `systemctl daemon-reload` and restart the timer. These settings were applied and tested on the production host on 2026-11-05.

The batch now commits up to 24 **node/protocol pairs per Exit node** for two cycles per run, while retaining a load guard, HTTP API health checks, locks against overlapping migration and WireGuard writers, and CPU quotas. One test run committed 192 pairs across four Exit nodes with API HTTP 200 and no worker errors.

Use these overrides only on a suitably sized server. They accelerate the six sing-box protocols, not the four standalone protocols (Mieru, TrustTunnel, AmneziaWG, Sudoku). Stored credentials are not proof of actual client connectivity. Watch `journalctl -u twinpanel-migration-batch.service` and API readiness; revert the overrides if API becomes unstable.
