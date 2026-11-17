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

## Acceptance criteria

1. Both services are active and show a GRE session, not repeated connection failures.
2. Iran-originated UDP messages round-trip via the dedicated loopback forward to the France echo target.
3. Compare baseline and TwinTunnel paths under the same load: 0-10 Mbps first, then measured controlled throughput using dedicated iperf3 in a separate maintenance window.
4. Track RTT, packet loss, jitter, throughput, and CPU over several minutes; make no speed guarantees from upstream benchmarks.

## Security and licensing

Rakhsh is upstream **AGPL-3.0-only**. Preserve notices/source availability obligations for any distributed derivatives or network services, and do not represent this branding layer as original Rakhsh source. This lab uses a pinned public release, no source modifications, and private keys stored only on hosts.
