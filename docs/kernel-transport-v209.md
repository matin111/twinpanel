# TwinPanel Kernel Transport V209

V209 adds two explicit-install, kernel-native server-to-server tunnel candidates:

- `kernel_ipip`: Linux IPIP (IP protocol 4), private IPv4 /30 inner L3.
- `kernel_vxlan`: Linux VXLAN over UDP with per-tunnel VNI/port, private IPv4 /30 inner L3.

It also makes the existing `tp6_fast` additive registry visible in API workers so TP6 appears in the Tunnel Transports page, not only inside the standalone transport manager.

## Safety contract

- `AUTO_INSTALL_NAMES` remains exactly `tp27_fast`.
- New candidates are installed only after an administrator explicitly clicks Install/Test.
- Installation does not change `active_transport` or `preferred_transport`.
- Every install must pass the existing TwinPanel full-L3 probe: two-way peer ping, TCP egress, and UDP egress.
- Failed candidates are recorded as `failed`; the current Production route stays unchanged.
- IPIP, VXLAN, and TP6 do not provide encryption by themselves. Use them only as transport layers inside an architecture where confidentiality is provided by the carried VPN/application layer.

## Runtime allocation

| Candidate | Inner subnet pool | Policy table base | Outer transport |
|---|---|---:|---|
| TP6 Fast | `10.249.0.0/16` | `34000` | IPv6 IP6GRE/IPIP6 |
| Kernel IPIP | `10.244.0.0/16` | `35000` | IPv4 protocol 4 |
| Kernel VXLAN | `10.243.0.0/16` | `36000` | UDP `37000-37999` |

## Rollback

The existing `DELETE /v1/tunnels/{tunnel_id}/modern-transports/{transport}` lifecycle stops/disables the per-tunnel systemd service, removes the tunnel interface, policy route, and TwinPanel-owned NAT rule. The service `ExecStop` also removes each candidate's inbound firewall rule.
