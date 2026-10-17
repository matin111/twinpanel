from __future__ import annotations

import shlex

from . import tp2027_egress_v37


# TWINPANEL_SERVICE_CLIENT_EGRESS_V46
#
# Production root cause (Tunnel #9):
# - Iran public ingress -> DNAT/SNAT -> TP2027 QUIC -> Exit listeners works.
# - TP2027 overlay itself has verified public egress.
# - Exit POSTROUTING has no MASQUERADE for the VPN client pools, so a client
#   can authenticate/connect while Internet traffic leaves with RFC1918 source.
#
# Keep this change isolated from tunnel transport selection. It extends the
# already panel-owned "repair real egress" path with idempotent Exit-side
# forwarding/NAT for the service client pools.

_RUNTIME_APPLIED = False
_ORIGINAL_EXTENDED_FIREWALL_SCRIPT = tp2027_egress_v37._extended_firewall_script

_CLIENT_POOLS: tuple[tuple[str, str], ...] = (
    ("cisco", "10.91.0.0/24"),
    ("openvpn", "10.92.0.0/24"),
    ("wireguard", "10.93.0.0/24"),
    ("l2tp", "10.94.0.0/24"),
)


def _service_client_egress_script(tunnel_id: int) -> str:
    base = str(_ORIGINAL_EXTENDED_FIREWALL_SCRIPT(int(tunnel_id)) or "").rstrip()

    if base.endswith("exit 0"):
        base = base[: -len("exit 0")].rstrip()

    lines = [
        base,
        "",
        "# TwinPanel V46: VPN service-client real Exit egress",
        'OUT_IF="$(ip -4 route show default | awk \'/^default / {print $5; exit}\')"',
        'test -n "$OUT_IF" || { echo TP_SERVICE_EGRESS_NO_DEFAULT_IF >&2; exit 1; }',
        "sysctl -w net.ipv4.ip_forward=1 >/dev/null",
        "iptables -N TP_SERVICE_EGRESS 2>/dev/null || true",
        "iptables -C FORWARD -j TP_SERVICE_EGRESS 2>/dev/null || iptables -I FORWARD 1 -j TP_SERVICE_EGRESS",
        "",
    ]

    for name, network in _CLIENT_POOLS:
        marker = f"TP-SERVICE-EGRESS-{name.upper()}"
        qnet = shlex.quote(network)
        qout = shlex.quote(marker + "-OUT")
        qret = shlex.quote(marker + "-RETURN")
        qnat = shlex.quote(marker + "-NAT")

        lines.extend(
            [
                (
                    "iptables -C TP_SERVICE_EGRESS "
                    f"-s {qnet} -o \"$OUT_IF\" "
                    f"-m comment --comment {qout} -j ACCEPT "
                    "2>/dev/null || iptables -I TP_SERVICE_EGRESS 1 "
                    f"-s {qnet} -o \"$OUT_IF\" "
                    f"-m comment --comment {qout} -j ACCEPT"
                ),
                (
                    "iptables -C TP_SERVICE_EGRESS "
                    f"-i \"$OUT_IF\" -d {qnet} "
                    "-m conntrack --ctstate ESTABLISHED,RELATED "
                    f"-m comment --comment {qret} -j ACCEPT "
                    "2>/dev/null || iptables -I TP_SERVICE_EGRESS 1 "
                    f"-i \"$OUT_IF\" -d {qnet} "
                    "-m conntrack --ctstate ESTABLISHED,RELATED "
                    f"-m comment --comment {qret} -j ACCEPT"
                ),
                (
                    "iptables -t nat -C POSTROUTING "
                    f"-s {qnet} -o \"$OUT_IF\" "
                    f"-m comment --comment {qnat} -j MASQUERADE "
                    "2>/dev/null || iptables -t nat -I POSTROUTING 1 "
                    f"-s {qnet} -o \"$OUT_IF\" "
                    f"-m comment --comment {qnat} -j MASQUERADE"
                ),
                "",
            ]
        )

    lines.extend(
        [
            'echo "TP_SERVICE_EGRESS_V46_READY out_if=$OUT_IF"',
            "exit 0",
            "",
        ]
    )

    return "\n".join(lines)


def apply_service_client_egress_v46() -> None:
    global _RUNTIME_APPLIED

    if _RUNTIME_APPLIED:
        return

    # V37 registers the repair endpoint after this hook is installed. The same
    # script renderer is also used for future TP2027 install/repair helpers.
    tp2027_egress_v37._extended_firewall_script = _service_client_egress_script

    _RUNTIME_APPLIED = True

    print(
        "TWINPANEL_SERVICE_CLIENT_EGRESS_V46_ACTIVE "
        "cisco=10.91.0.0/24 openvpn=10.92.0.0/24 "
        "wireguard=10.93.0.0/24 l2tp=10.94.0.0/24 "
        "forward=1 masquerade=1",
        flush=True,
    )
