# TwinTunnel — isolated Iran ↔ France tunnel lab

**Display name:** TwinTunnel  
**Underlying engine:** [CluvexStudio/Rakhsh](https://github.com/CluvexStudio/rakhsh) v0.1.0 (AGPL-3.0-only). TwinTunnel is a TwinPanel test deployment name, not a claim that Rakhsh was authored by TwinPanel.

This is a *parallel lab*, not the production tunnel engine. It does not alter VPN protocols, node configuration, IP routes, DNS, firewall, existing forwards, or account credentials.

## Deployment shape

- Iran: `twintunnel-lab@entry.service`, raw GRE responder; test UDP forward **127.0.0.1:37921** only.
- France: `twintunnel-lab@exit.service`, raw GRE dialer; target UDP echo **127.0.0.1:37922** only.
- `/opt/twintunnel-test/bin/twintunnel-core` is the original checksum-verified Rakhsh binary, **not** a modified/forked engine.
- Each host stores its own secret config under `/etc/twintunnel-test/{entry,exit}.toml` (0600), never in GitHub.
- GRE uses IP protocol **47**, not TCP/UDP port 37027. The given tunnel address only helps generate the paired config.
- Control sockets: `/run/twintunnel-test-entry.sock` and `/run/twintunnel-test-exit.sock`.
- The example `shabdiz-gre` carrier transports a **single** UDP forward. TCP forwarding must be tested in a separate isolated carrier/config.

## Obtain the binary

Download the **v0.1.0** `rakhsh-x86_64-unknown-linux-musl` release asset, check SHA-256:

```
bdfbf8d346925545d23c202699c535d5a5fd94b3106f42666e04aeb52023e226
```

Install into `/opt/twintunnel-test/bin/twintunnel-core`, not `/usr/local/bin/rakhsh`. The binary has its upstream name internally, but is branded TwinTunnel in our lab service names.

## Generate separate secrets

On a trusted host with the binary:

```sh
umask 077
/opt/twintunnel-test/bin/twintunnel-core init \
  --tunnel-addr IRAN_PUBLIC_IP:37027 \
  --carrier shabdiz-gre \
  --peer-ip FRANCE_PUBLIC_IP \
  --forward 127.0.0.1:37921=127.0.0.1:37922/udp \
  > generated-pair.private
```

Split the output into the generated `entry.toml` and `exit.toml`, place the **entry half only in Iran** and the **exit half only in France**, chmod 0600, and remove the temporary combined private file after distribution. Set role-specific `control_socket` values and optionally `pace_burst = 2` and `pace_auto = true` above the `[[forward]]` block. Always validate with `twintunnel-core check -c /etc/twintunnel-test/entry.toml` / `exit.toml` before starting.

## Run (lab only)

Install `systemd/twintunnel-lab@.service` as `/etc/systemd/system/twintunnel-lab@.service` on both hosts. Install `systemd/twintunnel-lab-udp-echo.service` on France, and place `udp_echo.py` at `/opt/twintunnel-test/udp_echo.py`.

```sh
# France
systemctl daemon-reload
systemctl start twintunnel-lab-udp-echo.service
systemctl start twintunnel-lab@exit.service

# Iran
systemctl daemon-reload
systemctl start twintunnel-lab@entry.service
python3 udp_probe.py --host 127.0.0.1 --port 37921 --count 20
```

To inspect without revealing secrets:

```sh
/opt/twintunnel-test/bin/twintunnel-core status --socket /run/twintunnel-test-entry.sock
journalctl -u twintunnel-lab@entry --since '10 minutes ago' --no-pager
```

To safely stop:

```sh
systemctl stop twintunnel-lab@entry.service
systemctl stop twintunnel-lab@exit.service twintunnel-lab-udp-echo.service
```

Do not `enable` or connect customer traffic until the GRE path and fallback carriers are measured. Only apply to production after a separate rollout/rollback plan.

## Additional isolated carriers (17 November 2026)

TwinTunnel's fallback tests use independent Rakhsh configs and the **same** France
loopback UDP echo target; no existing VPN ports or customer routes are changed.

| Carrier | Iran unit | France unit | Local Iran UDP probe | Transport |
|---|---|---|---|---|
| GRE (baseline) | `twintunnel-lab@entry.service` | `twintunnel-lab@exit.service` | `127.0.0.1:37921` | IP protocol 47 |
| TCP (fallback experiment) | `twintunnel-lab@entry-tcp.service` | `twintunnel-lab@exit-tcp.service` | `127.0.0.1:37931` | TCP port 37031 on Iran |
| UDP (fallback experiment) | `twintunnel-lab@entry-udp.service` | `twintunnel-lab@exit-udp.service` | `127.0.0.1:37933` | UDP port 37033 on Iran |

All `entry-*.toml` and `exit-*.toml` configs contain generated individual
Noise keys, and are **not committed to GitHub**. Generate them with
`/opt/twintunnel-test/bin/twintunnel-core init --tunnel-addr IRAN_PUBLIC_IP:37031 --carrier shabdiz-tcp
--forward 127.0.0.1:37931=127.0.0.1:37922/udp` for TCP, or switch to
`shabdiz-udp`, port `37033`, forward `37933` for UDP. Distribute each
half to its corresponding host as `/etc/twintunnel-test/entry-tcp.toml`,
`exit-tcp.toml`, etc. Set unique `control_socket` paths and validate
with `twintunnel-core check -c` before starting.

The TCP fallback connected but had ~37% UDP-echo loss at the 5-Mbps load
and must **not** be automatically enabled for VPN users.

### Reproducible bounded comparison

On the Iran host, run only when the lab services are running:

```sh
python3 /opt/twintunnel-test/compare_carriers.py \
  --rounds 2 --duration 4 --size 900 --carriers GRE UDP
```

This sends localhost-only UDP probes at 2 and 5 Mbps, reverses test order
between rounds, prints loss/RTT/returned Mbps, and saves raw JSON under
`/opt/twintunnel-test/results/`. The script limits burst durations and
rates to avoid imposing significant load on a production machine. These
are **echo measurements, not end-to-end throughput against current VPN**.

To stop optional fallback services without affecting GRE:

```sh
systemctl stop twintunnel-lab@entry-tcp.service twintunnel-lab@entry-udp.service   # Iran
systemctl stop twintunnel-lab@exit-tcp.service twintunnel-lab@exit-udp.service      # France
```

See [TEST_RESULTS.md](TEST_RESULTS.md) for observed numbers. No new fallback
service has been enabled at boot.

## Acceptance criteria

1. Both services are active and show a GRE session, not repeated connection failures.
2. Iran-originated UDP messages round-trip via the dedicated loopback forward to the France echo target.
3. Compare baseline and TwinTunnel paths under the same load: 0-10 Mbps first, then measured controlled throughput using dedicated iperf3 in a separate maintenance window.
4. Track RTT, packet loss, jitter, throughput, and CPU over several minutes; make no speed guarantees from upstream benchmarks.

## Security and licensing

Rakhsh is upstream **AGPL-3.0-only**. Preserve notices/source availability obligations for any distributed derivatives or network services, and do not represent this branding layer as original Rakhsh source. This lab uses a pinned public release, no source modifications, and private keys stored only on hosts.


## Four-link Rakhsh stream lab (17 November 2026)

**Separate from Shabdiz-GRE:** the existing Shabdiz datagram engine does not use
the Rakhsh lane pool or TCP stream resumption. This new, isolated multi-link
laboratory uses **Rakhsh stream mode** and does **not carry customer VPN traffic**.

On Iran, `twintunnel-lab@entry-multilink.service` listens on four independent
carrier sockets: **TCP/37041, TLS/37042, QUICv2 UDP/37043, WS/37044**.
On France, `twintunnel-lab@exit-multilink.service` dials the same four.
There are **four total lanes**, `link_policy = "spread"`, and
`resume = true` with a 60-second grace period **on both ends**.
The isolated TCP forward is Iran `127.0.0.1:37941` → France
`127.0.0.1:37942`; `tcp_echo.py` listens only on French loopback.

Generate a *fresh private pair*, never commit either half:
```sh
/opt/twintunnel-test/bin/twintunnel-core init --tunnel-addr IRAN_PUBLIC_IP:37041 --carrier tcp \
  --link tls:37042 --link quicv2:37043 --link ws:37044 \
  --lanes 4 --link-policy spread --resume --resume-grace 60 \
  --forward 127.0.0.1:37941=127.0.0.1:37942
```
Use `control_socket = "/run/twintunnel-multilink-entry.sock"` on Iran
and `control_socket = "/run/twintunnel-multilink-exit.sock"` on France;
validate each half with `/opt/twintunnel-test/bin/twintunnel-core check -c <path>`.
Secret TOML files remain `0600` under `/etc/twintunnel-test/`. The existing
`twintunnel-lab@.service` template starts each new instance by config name.
The TCP echo service is defined in
`systemd/twintunnel-lab-tcp-echo.service`. Nothing was enabled at boot.

### Verified on real Iran ↔ France hosts

- Both Rakhsh instances reported **four established lanes**, one each over
  TCP, TLS, QUICv2 and WS; TCP loopback echo data matched exactly.
- At 07:32 UTC, while **8 long-lived TCP streams** were active, the **dedicated
  lab TCP lane** (port 37041 only) was reset with `ss -K`. Rakhsh reported
  two streams moving to another lane; **all 8/8 sockets completed, 760/760
  echo blocks matched**; the exit recorded two retransmitted chunks.
- At 07:33 UTC, while another eight streams were active, the isolated
  **TCP and TLS lanes** (ports 37041 and 37042 only) were reset.
  **All 8/8 streams and 760/760 blocks completed**; at least two streams were
  observed moving to the surviving WS lane; remaining carriers recovered.
- This proves **TCP stream integrity under these two controlled faults**,
  not zero latency: observed per-block stalls reached ~1.56 seconds.
  It does not prove behavior under a prolonged full outage.

These are **different carriers to the same Iran / France endpoint pair**, not
independent physical networks or redundant exit servers. If that path or an
entire host fails, all four carriers may fail. `resume` does **not**
cover UDP datagrams or L3 TUN, and stream carriers may be unsuitable for
high-volume UDP VPN traffic. Do **not** migrate existing OpenVPN/WireGuard,
IPsec, or any other customer route based on this stream-only test.

For a repeatable test (normal operation, without forced faults):
```sh
python3 /opt/twintunnel-test/multilink_resume_probe.py
```
For diagnostics:
```sh
/opt/twintunnel-test/bin/twintunnel-core status --socket /run/twintunnel-multilink-entry.sock
/opt/twintunnel-test/bin/twintunnel-core status --socket /run/twintunnel-multilink-exit.sock
```
**Fault injection is not an automated step**; it must target confirmed
dedicated lab ports and must never select production sockets.

Lab rollback: stop `twintunnel-lab@entry-multilink.service` (Iran) and
`twintunnel-lab@exit-multilink.service` plus
`twintunnel-lab-tcp-echo.service` (France). Leave existing GRE, VPN, nodes,
DNS and client configurations untouched.


## 17 November 2026: real OpenVPN TCP over Multi-Link and UDP two-carrier canary

**Scope:** This is still an isolated, temporary lab, not customer routing.
The multi-link and two standalone Shabdiz datagram transports use the **same
Iran/France host pair**; different carriers do not protect against the complete
loss of either node or the underlying physical path.

### OpenVPN TCP actual session (France → Iran → France)

- An isolated OpenVPN 2.6.19 **TCP server** listens on French loopback
  `127.0.0.1:37942` with a separate, short-lived PKI.
- A test OpenVPN client on **France** dials the Iran-only lab ingress
  `94.183.231.158:37951`; its TCP bytes are forwarded by
  `127.0.0.1:37941` through Rakhsh's four carriers to the French server.
- **No OpenVPN process runs on Iran** for this test. Iran runs only the
  Rakhsh ingress/proxy; no customer OpenVPN credentials or configurations
  are used.
- OpenVPN TLS negotiated successfully; both dedicated TUN interfaces
  `tunTTcl` and `tunTTsv` came up with the test point-to-point addresses.
- At **08:53:14 UTC** the dedicated TCP/37041, TLS/37042, and WS/37044
  *lab-only* lanes were reset, leaving QUICv2 alive. During the controlled
  80-packet OpenVPN data probe:
  **80 sent, 80 captured at the receiving TUN, 80 unique ICMP sequence
  numbers, 0 missing; +80 packets / +6720 bytes in server-TUN counters.**
  The test client recorded **one total OpenVPN initialization**, i.e. no
  full connection reestablishment in this test.
- The ICMP payload targets an intentionally nonresponding documentation/
  benchmark address `198.18.254.254`; the test concerns **delivery to
  the OpenVPN server's TUN**, not successful ICMP echo replies.
  A scoped `/32` test route is created and removed by the script.
- The original probe incorrectly searched for `icmp seq` whereas Linux
  tcpdump outputs `ICMP echo request, id ..., seq ...`.
  `openvpn_data_failover_probe.py` uses the corrected extraction and
  requires both exact unique sequence and kernel counter totals.
- The private test certificates and keys are **not in GitHub**.
  This temporary test certificate expires **19 November 2026**.

### UDP continuity experiment (GRE primary + Shabdiz-UDP backup)

Rakhsh's `shabdiz-*` datagram transport does **not** participate in the
stream multi-link lane pool or `resume`. Instead an isolated test-only
selector `udp_failover_gateway.py` provides the single stable UDP
frontend `127.0.0.1:37961`. It checks **two separate Rakhsh echo
forwards**, GRE at `127.0.0.1:37921` and Shabdiz-UDP at
`127.0.0.1:37933`, both ending at the France loopback lab echo
`127.0.0.1:37922`. Health checks use the echo's strict
`TTLB1` prefix, without changing the VPN services.

**Observed while sending 300 sequence-coded UDP packets:**
- GRE was intentionally stopped at **09:02:58 UTC** and restored at
  **09:03:06 UTC**. Both are *existing lab services only*.
- Gateway switched **GRE → UDP** at approximately **09:03:00 UTC**;
  **UDP → GRE** at approximately **09:03:38 UTC**.
- The GRE Shabdiz session did not finish reestablishing until about
  **09:03:36 UTC**, despite the entry process being restarted at 09:03:06.
  This prolonged recovery delays failback.
- **300 sent, 290 unique replies, 10 missing, 3.33% missing**.
  Six consecutive missing sequences (29–34) straddled the path outage;
  additional individual missing sequences were 41, 153, 214, and 299.
  The gateway reported `no_path=0`, but this must **not** be read as
  zero lost UDP packets.
- Six unit tests for initial selection, failover, failback hysteresis and
  no-path handling passed.
- Post-test GRE returned to **active** with a 10/10 direct echo check.
  Existing French OpenVPN services remained active. The temporary
  OpenVPN benchmark route was removed.

The UDP selector deliberately supports only **one lab client** and
depends on an **echo-capable lab target**; it is **not a production UDP
multiplexer**, does not preserve arbitrary concurrent WireGuard/OpenVPN
user sessions, and does not provide end-to-end packet integrity or
retransmissions. Any real customer-grade solution needs an authenticated
multi-user session map on both tunnel ends, a separate health target,
flow affinity/return-path handling, good duplicate/sequence behavior,
recovery and quality thresholds, and genuine client canary results.
At **3.33% lab loss**, this build must **not** be rolled out to users.

To repeat the bounded *lab-only* UDP fault test, start the lab echo and
both preexisting Rakhsh GRE and UDP carriers on each host, launch
`python3 /opt/twintunnel-test/udp_failover_gateway.py --duration 110`
on Iran and then run `udp_failover_inject.sh` on Iran.
The script verifies the lab unit identity, stops only the dedicated
GRE lab service while a 300-packet probe is underway, and restores it
with an EXIT trap. It must **never** be directed at production tunnels.

The test gateway is intentionally not enabled at boot; it stops after
its bounded run. Do not expose `37961` publicly or attach any production
VPN protocol until the limitations above have been addressed.


### Redundant UDP echo canary — separate verification, not VPN support

`udp_redundant_canary.py` is a *second* localhost-only demonstration
at `127.0.0.1:37962` that sends **each correctly tagged test packet**
through both the GRE and UDP Rakhsh lab forwards, accepts the first
response, and rejects later duplicates by its lab packet sequence number.
It rejects packets without the dedicated `TTLB1TT-UDP-CANARY:` prefix
and supports only one test client; **generic UDP VPN traffic is explicitly
unsupported**. Re-run the test with `udp_redundant_inject.sh`; the same
bounded GRE lab outage and restoration are applied.

At **09:10:58 UTC** GRE was intentionally stopped while the canary sent,
and it was restored at **09:11:06 UTC**. The canary sender recorded
**300 sent, 298 unique replies within its deadline, 2 missing (0.67%)**,
versus **290/300 (3.33% missing)** in the earlier active-only selector
run. The two missing sequence numbers were `232` and `299`, not the
earlier contiguous six-packet outage. The gateway itself later saw
**299 unique echoes** and suppressed **29 duplicate replies**; one
reply arrived after the client's deadline.

This is *not* a statistically validated speed or reliability gain from
one pair of runs. Replication approximately doubles outbound carrier
datagrams, which may worsen bottlenecks and CPU load. Importantly it
does **not** provide a production-ready authenticated/anti-replay-aware
two-ended UDP session multiplexer, or promise that existing OpenVPN UDP
or WireGuard clients will remain connected. Both carrier types still
share the same Iran/France host and underlying Internet route.

The standalone unit suite covers six route policy and four strict
canary packet parser cases (**10/10 passed**). Every test is manually
started, never boot-enabled, and excluded from customer routing.


## 17 November 2026: authenticated two-ended multi-user UDP experiment

**NOT PRODUCTION-READY. No customer VPN traffic or routing was changed.**

The experimental module udp_multiuser_mux.py has two roles:

- Iran entry: 94.183.231.158:37981/UDP (WireGuard lab) and
  :37982/UDP (OpenVPN UDP lab), restricted to test clients from France.
  **Iran does not run a customer WireGuard or OpenVPN server in this design.** Two temporary kernel WireGuard clients were used on Iran for the subsequent lab validation and then deleted.
- France exit: 127.0.0.1:37922/UDP, temporarily replacing only the
  *existing isolated lab UDP echo*. The original echo is restored on rollback.
- Both ends share an independent, per-lab 256-bit HMAC secret stored
  in a 0600 file under /etc/twintunnel-test/udp-mux-key.hex.
  The secret is NOT included in the repository.
- The two preexisting Rakhsh datagram carriers are separate GRE and UDP
  forwards. Each test payload is sent over both carriers, and verified
  duplicates are suppressed. On France, every user flow has its own
  stable UDP socket, so the server-facing source port does not change
  merely because one Shabdiz carrier disappears.
- Limitations: maximum 64 flows, maximum 1250-byte user payload, a
  512-sequence replay window, 120-second idle expiry, no fragmentation,
  only two fixed service destinations, and no multi-node orchestration.
  This is an experimental implementation, not a generic UDP VPN proxy.

**Test results:** 13/13 offline unit tests passed. Six independently
identified clients concurrently exercised two UDP lab echo services.
After fixing the probe to count out-of-order and delayed replies,
**226/240 distinct responses arrived within the deadline** (14 missing,
5.83% missing). This is insufficient for customer traffic.

A **real WireGuard kernel client and kernel server on France** were then
started with isolated fresh keys, dedicated interfaces, a temporary
198.18.66.1/32 route, and Iran as the public UDP entry.
The client emitted 888 bytes; the server received **0 bytes**, with
**zero authenticated handshakes**. This first France-origin WireGuard hairpin test FAILED. A separate Iran-origin test later succeeded (details below).
Both WireGuard test interfaces and the temporary route were cleaned.
At this stage, real OpenVPN UDP had not yet been tested. A later isolated real OpenVPN UDP test succeeded (details below).

**Temporary blocker, resolved:** Iran's Termalin management agent went offline at 09:31:33 UTC on 17 November 2026. France could still ping Iran. The management connection recovered at 09:36:11 UTC, and the original 600-second lab process exited and released its public test ports.
On France, the experimental UDP mux was stopped and the original
twintunnel-lab-udp-echo.service was restored. The production
OpenVPN services and original Rakhsh lab carriers remained active.

**Before any customer use:** run sustained real-VPN canaries, quantify jitter and individual missing sequences during repeated failovers, validate two-ended NAT rebinding and user session expiry, and perform multi-client/MTU/rebinding/load/latency testing.
This code does not implement the production user quotas, device limits,
license resolution, NAT rebinding, multi-node failover or link-quality
control. It must NOT be added to customer start-up/deploy hooks.

Repeatable non-production assets:
udp_multiuser_mux.py, udp_mux_echo_targets.py,
udp_mux_multi_client_probe.py, wg_multiuser_lab.sh,
tests/test_udp_multiuser_mux.py, and
results/2026-11-17-multiuser-udp-lab.json.


### Live real-VPN data validation (later on 17 November 2026)

**OpenVPN UDP actual session:** Temporary UDP OpenVPN client and server
were both on France, but all encrypted UDP traffic passed through the
Iran entry and separate Rakhsh GRE/UDP paths. OpenVPN TLS completed;
during **80 ICMP packets** sent inside the VPN, the dedicated GRE lab
was stopped for **6 seconds** and Shabdiz-UDP remained active.
The French OpenVPN server TUN received **80/80 unique ICMP sequences**,
with **+80 packets / +6720 bytes** in kernel counters.
There was **one OpenVPN initialisation and zero inactivity-triggered
restarts** during the controlled test. The probe deliberately targeted
a nonresponding test IP, so ping replies are not a success criterion.
See openvpn_udp_mux_orchestrator.py, openvpn_udp_mux_data_probe.py and
the examples/openvpn-udp-*-lab.conf files. The orchestrator restores
the original France lab UDP echo on exit.

**WireGuard actual session:** The earlier France-origin WG hairpin test
had no handshake. Packet capture showed outbound WireGuard handshakes
on French eth0 and no matched handshakes at Iran in a separate capture,
although 8 synthetic 148-byte UDP controls on the same port were seen.
This raises, but does not prove, protocol-specific filtering on the
France-to-Iran link. It does not establish what real clients in Iran see.

A second test instead used **two ephemeral WireGuard clients on Iran**
(no WireGuard customer server on Iran), connecting to a dedicated kernel
WireGuard server on France. The two Iran clients used distinct public
keys, distinct test IPs and separate UDP source flows. The dedicated
Rakhsh GRE lab was intentionally stopped for **8 seconds** while both
sent data and Shabdiz-UDP stayed active. The France WireGuard server
reported **2 recent authenticated peer handshakes, 294 decrypted
kernel TUN packets and 37,480 received TUN bytes**; the France UDP
multiplexer also recorded 294 server-bound packets. It suppressed 118
duplicate upstream copies. This confirms actual encrypted WireGuard
traffic passes through the multiplexed underlay despite that particular
GRE failure. It does **not** measure per-sequence loss or precise
interruption time, and cannot promise permanent/zero-loss connections.

There was a reporting-only bash variable interpolation bug in the
original Iran WireGuard client test script after the traffic phase.
Its EXIT trap cleaned both test interfaces and test routes. The script
is corrected in the repository. The France server test orchestrator
completed cleanly, restored twintunnel-lab-udp-echo.service and kept
wg-access0 and main OpenVPN services untouched.

New scripts: wg_mux_iran_clients.sh, wg_mux_france_server.sh,
openvpn_udp_mux_orchestrator.py, openvpn_udp_mux_data_probe.py.
All are **manual, time-bounded lab tools**. Never add them to
production startup hooks or replace actual customer config endpoints.
All main VPN configurations, licence data and user credentials
remain unchanged.

**Production gap:** The engine is a bounded Python proof of concept
(64 flows, 1250-byte payloads, 120-second idle state).
The corrected 6-client lab echo test previously observed
5.83% missing responses within its deadline. Real OpenVPN UDP and
WireGuard successes under a single short GRE fault do not replace
multi-hour load testing, MTU discovery, multi-user replay and NAT rebinding
security, dynamic routing/quality decisions, support for every customer
node, and tested rollback of the actual customer connection path.
