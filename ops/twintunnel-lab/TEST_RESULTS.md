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


## Continued carrier comparison (17 November 2026)

All three Rakhsh/Shabdiz carriers established a real session between the
same Iran entry and France exit. All UDP echo endpoints bound only to loopback.
The TCP and UDP fallbacks used their own secrets, systemd units, and transport
ports, not the customer tunnel.

### Initial equal-rate TCP versus GRE

| Probe | TCP | GRE |
|---|---:|---:|
| 40 × 900-byte UDP echo, average RTT | 144.38 ms | 141.16 ms |
| 1 Mbps, packet loss | 0% | 1.80% |
| 1 Mbps, returned throughput | 1.001 Mbps | 0.983 Mbps |
| 5 Mbps, packet loss | **36.59%** | 7.96% |
| 5 Mbps, returned throughput | **3.171 Mbps** | 4.602 Mbps |
| 5 Mbps, average RTT | **1757.58 ms** | 848.68 ms |

Shabdiz-TCP demonstrated severe head-of-line delay at 5 Mbps UDP-echo load
and is **not** selected for VPN datagram traffic.

### UDP fallback and GRE, two order-reversed A/B rounds

The repeatable, bounded `compare_carriers.py` script ran two rounds,
reversing test order. Each run sent 900-byte echo packets for four seconds.
The exact eight runs are in
[results/2026-11-17-gre-udp.json](results/2026-11-17-gre-udp.json).

| Target | Carrier | Average echoed rate | Mean loss | Mean RTT |
|---|---|---:|---:|---:|
| 2 Mbps | GRE | 1.984 Mbps | 0.86% | 104.8 ms |
| 2 Mbps | UDP | 1.972 Mbps | 1.49% | 104.7 ms |
| 5 Mbps | GRE | 4.815 Mbps | 3.71% | 246.2 ms |
| 5 Mbps | UDP | 4.804 Mbps | 3.93% | 97.8 ms |

The GRE mean RTT at 5 Mbps is dominated by **one unstable round**
(98.22 ms versus 394.23 ms), so comparing only average RTT is misleading.
UDP and GRE have comparable echo throughput within this small test sample,
neither proving superiority over the established production tunnels.

### GRE payload-size check (single run per configuration)

| Rate | Payload | Echoed throughput | Loss | Mean RTT |
|---|---|---:|---:|---:|
| 5 Mbps | 900 bytes | 4.675 Mbps | 6.48% | 848.74 ms |
| 5 Mbps | 1200 bytes | 4.799 Mbps | 4.03% | 179.25 ms |
| 10 Mbps | 1200 bytes | 9.645 Mbps | 3.55% | 95.60 ms |
| 10 Mbps | 900 bytes | 9.507 Mbps | 4.93% | 94.49 ms |

Larger payloads reduced loss **in this one limited test** and may
reduce packet-per-second pressure, but require repeated validation before
MTU recommendations. The Rakhsh GRE payload MTU was 1427 bytes;
no production VPN MTU was modified.

### Current decision

- **GRE remains the default lab carrier only**, with no customer traffic.
- TCP fallback stopped after testing: unacceptable UDP latency/loss.
- UDP fallback also stopped after comparison: not enough measurable
  improvement to prefer it.
- Production tunnel routes, protocol configuration, customer sessions, and
  node configuration remain unchanged.
- The France host was concurrently under load (16 logical CPUs, ~5–8
  load-average); these echo results are not a peak-speed measurement.
- A production decision requires low-loss multi-minute tests and a genuinely
  comparable existing-tunnel baseline; do not claim speed improvement yet.

## Live repeat and topology audit — 17 November 2026, 06:24–06:28 UTC

This follow-up used the **same isolated Iran ↔ France Rakhsh GRE lab**, and did not
modify production VPN routes, firewall rules, client configurations, or tunnel services.

### GRE-only repeated load (3 rounds, 900-byte UDP echo, 4 seconds per rate)

Exact individual samples: [results/2026-11-17-gre-repeat-load.json](results/2026-11-17-gre-repeat-load.json).

| Rate target | Mean echoed payload rate | Mean missing by probe deadline | Mean RTT of received replies |
|---|---:|---:|---:|
| 2 Mbps | 1.881 Mbps | 6.00% | 95.3 ms |
| 5 Mbps | 4.392 Mbps | 12.16% | 851.3 ms |

**Caution:** The UDP probe counts replies not received before its finite collection
deadline as missing; this is **not proof that all such packets were lost on the wire**.
At 5 Mbps, received-packet p95 RTT ranged ~1520–1554 ms, indicating severe queueing
or service delay. A separate 5-Mbps run returned 4.159 Mbps, 16.82% missing,
857.68 ms mean RTT.

### Underlay path check

- During that separate 5-Mbps GRE run, 14 concurrent direct ICMP requests from Iran
  to the same France public host returned 13 replies (**7.14% loss**);
  RTT of replies averaged **93.52 ms**.
- Subsequent independent, 60-packet probes on the public endpoint pair showed
  Iran → France **2/60 lost (3.33%)**, 91.43 ms mean received RTT;
  France → Iran **4/60 lost (6.67%)**, 92.70 ms mean received RTT.
- Direct ICMP is a **different packet type/protocol than GRE**; these samples suggest
  underlay instability but do not attribute the application-level loss to any single cause.
- During the concurrent run, France's cumulative `Udp:RcvbufErrors` counter was
  **unchanged at 8946** across pre/post snapshots; earlier cumulative UDP buffer
  errors existed, but cannot be attributed to this run without per-socket measurements.
- The lab Rakhsh status had **one established lane, zero reconnects** over ~4h50m;
  its displayed 0.0% link loss is not a substitute for independent echo metrics.

### Production baseline topology mismatch

The observed production VXLAN/GRE interfaces on the Iran host target **different
remote endpoints** from the France host used for this TwinTunnel lab. Thus **there
is no apples-to-apples current-tunnel vs TwinTunnel speed result**. Do not compare
their unpaired speeds or infer user benefit from these samples.

**Decision:** keep GRE in the isolated lab only; do **not** route customers over
TwinTunnel or promote this carrier. Before a production trial, arrange access to
a production peer endpoint for a safe parallel lab (or deploy an existing carrier
to the same France endpoint) and benchmark both over equal endpoints, rates,
payloads, and conditions, including CPU/queueing and longer-duration jitter/loss.
