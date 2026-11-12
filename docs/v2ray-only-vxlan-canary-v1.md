# Isolated V2Ray TCP-only ingress routes — Iran 9 / Germany 7 / USA 11

This is **opt-in**, not an installer default. It only overrides these public
TCP ports of the audited Iran 9 ingress:

- Germany: 24007 (VLESS XHTTP REALITY), 26007 (WS/TLS), 28007 (TCP/TLS)
- USA: 24011 (VLESS XHTTP REALITY), 26011 (WS/TLS), 28011 (TCP/TLS)

**All other ports, including UDP 28007/28011, Cisco, OpenVPN, WireGuard,
all other VPN protocols, and every Agent-managed GRE/transport rule remain
unchanged.** Xray is not restarted. Existing conntrack connections are not
removed. Do not enable on an unaudited node.

## Apply only on the audited Iran 9 ingress

Verify `10.243.0.121/30` on `tpvx30` (peer `10.243.0.122`)
and `10.243.0.129/30` on `tpvx32` (peer `10.243.0.130`).

```bash
install -m 750 backend/scripts/v2ray_only_vxlan_canary_v1.py /usr/local/sbin/tp-v2ray-only-vxlan-canary-v1
install -m 644 backend/scripts/systemd/tp-v2ray-only-vxlan-canary.service /etc/systemd/system/
install -m 644 backend/scripts/systemd/tp-v2ray-only-vxlan-canary.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start tp-v2ray-only-vxlan-canary.service
systemctl enable --now tp-v2ray-only-vxlan-canary.timer
for profile in de-ws de-xhttp de-tcp us-ws us-xhttp us-tcp; do
  python3 /usr/local/sbin/tp-v2ray-only-vxlan-canary-v1 status --profile="$profile"
done
```

## Explicit rollback (no Xray or tunnel restart)

```bash
systemctl disable --now tp-v2ray-only-vxlan-canary.timer
for profile in de-ws de-xhttp de-tcp us-ws us-xhttp us-tcp; do
  python3 /usr/local/sbin/tp-v2ray-only-vxlan-canary-v1 remove --profile="$profile"
done
```

The script only inserts/removes its exact-match TCP NAT overrides ahead of
the Agent-managed parent chain jumps. It neither flushes those chains nor
changes any tunnel configuration or TCP congestion settings.
