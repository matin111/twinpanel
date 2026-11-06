# Isolated V2Ray WS canary — Iran 9 / Germany 7

This is **opt-in**, not an installer default. It is scoped only to public TCP
port **26007** (VLESS WS/TLS) on the audited Iran 9 ingress. Other public
V2Ray ports and every other protocol keep the panel's managed tunnel rules.

## Apply on the audited Iran ingress only

After validating the local VXLAN IP `10.243.0.121/30` on `tpvx30`
and its peer `10.243.0.122`, install:

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
```

The script only inserts/removes its exact NAT overrides in the parent
PREROUTING/POSTROUTING chains; it does not flush any Agent-managed chains.
Existing conntrack sessions are left intact. The underlying Agent and GRE
rules remain unchanged. Never apply the script on an unaudited node.
