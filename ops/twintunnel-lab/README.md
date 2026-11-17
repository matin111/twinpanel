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
