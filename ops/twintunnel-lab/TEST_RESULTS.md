# TwinTunnel lab results — 17 November 2026

Environment: isolated TwinTunnel (upstream Rakhsh v0.1.0), Shabdiz-GRE, public Iran ↔ France hosts, independent localhost-only UDP echo. **No customer traffic or VPN routing was migrated.**

## Baseline and connectivity

- The GRE session was established in both directions, with a negotiated **1427-byte payload MTU**.
- Direct ICMP baseline Iran → France: 15/15 replies, **89.23 ms** average RTT, 0% loss in this small sample.
- Initial GRE UDP echo: 15/16 replies, **110.32 ms** average RTT.
- Warmed GRE UDP echo: 40/40 replies, **95.89 ms** average RTT, 0% loss in that sample.

## Controlled UDP echo tests (approximate, not peak VPN speed)

| Mode | Sent | Echoed | Lost | Avg echo RTT | Echoed throughput |
|---|---:|---:|---:|---:|---:|
| Auto pacing, 1 Mbps target, 4 seconds | 555 | 543 | 2.16% | 103.70 ms | 0.979 Mbps |
| Auto pacing, 5 Mbps target, 4 seconds | 2777 | 2672 | 3.78% | 96.65 ms | 4.811 Mbps |
| Auto pacing, 10 Mbps target, 5 seconds, 1100-byte payload | 5681 | 4973 | 12.46% | 548.23 ms | 8.754 Mbps |
| Fixed 1000 pps, 1 Mbps target, 4 seconds | 555 | 548 | 1.26% | 108.73 ms | 0.988 Mbps |
| Fixed 1000 pps, 5 Mbps target, 4 seconds | 2777 | 2665 | 4.03% | 97.29 ms | 4.798 Mbps |

Fixed 1000 pps did not clearly improve the higher-load test; **auto pacing was restored** on both hosts.

## Interpretation

These results prove the independent GRE path works and can carry UDP echo traffic. They do **not** demonstrate that TwinTunnel is faster than the production tunnels. At the 10-Mbps echo load, packet loss rose above 12% and RTT worsened sharply, so this path **fails a production-quality test** at that rate. The direct ICMP baseline is not an apples-to-apples UDP throughput comparison.

Follow-up comparison requires an equal-load, equal-endpoint throughput benchmark against existing tunnels and monitoring of retransmission, packet loss, queueing and CPU. Do **not** make this engine the default for users solely on the upstream published 213/100 Mbps figures.

## Security and deployment

- Secret configs live only on their respective hosts under `/etc/twintunnel-test/` and are `0600`.
- Independent systemd services: `twintunnel-lab@entry.service`, `twintunnel-lab@exit.service`, and `twintunnel-lab-udp-echo.service`.
- Each daemon uses a dedicated control socket and no production ports, DNS, routes or firewall changes.
- The Rakhsh binary matches the upstream SHA-256 pinned in the README.
- No automatic start at boot has been enabled. Stop commands are in README.
