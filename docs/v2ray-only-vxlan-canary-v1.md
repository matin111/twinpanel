# Isolated V2Ray WS canary — Iran 9 / Germany 7 / USA 11

This is **opt-in**, not an installer default. It is scoped only to public TCP
ports **26007** and **26011** (VLESS WS/TLS) on the audited Iran 9 ingress. Other public
V2Ray ports and every other protocol keep the panel's managed tunnel rules.

## Apply on the audited Iran ingress only

After validating `10.243.0.121/30` on `tpvx30` (peer `10.243.0.122`)
and `10.243.0.129/30` on `tpvx32` (peer `10.243.0.130`), install:

```bash
install -m 750 backend/scripts/v2ray_only_vxlan_canary_v1.py /usr/local/sbin/tp-v2ray-only-vxlan-canary-v1
install -m 644 backend/scripts/systemd/tp-v2ray-only-vxlan-canary.service /etc/systemd/system/
install -m 644 backend/scripts/systemd/tp-v2ray-only-vxlan-canary.timer /etc/systemd/system/
systemctl daemon-reload
systemctl start tp-v2ray-only-vxlan-canary.service
systemctl enable --now tp-v2ray-only-vxlan-canary.timer
python3 /usr/local/sbin/tp-v2ray-only-vxlan-canary-v1 status
```

## Explicit rollback (does not restart Xray or other VPN protocols)

```bash
systemctl disable --now tp-v2ray-only-vxlan-canary.timer
python3 /usr/local/sbin/tp-v2ray-only-vxlan-canary-v1 remove --profile=de-ws
python3 /usr/local/sbin/tp-v2ray-only-vxlan-canary-v1 remove --profile=us-ws
```

The script only inserts/removes its exact NAT overrides in the parent
PREROUTING/POSTROUTING chains; it does not flush any Agent-managed chains.
Existing conntrack sessions are left intact. The underlying Agent and GRE
rules remain unchanged. Never apply the script on an unaudited node.
