from __future__ import annotations

import shlex

from . import vpn_access_dataplane_v46 as dataplane
from . import vpn_access_performance_v51 as performance


# ============================================================
# TWINPANEL EXIT ACCESS DATAPLANE STABILITY V144
# ============================================================

MARKER = "TWINPANEL_EXIT_ACCESS_DATAPLANE_STABILITY_V144"

_applied = False

_original_egress_script = dataplane._egress_script
_original_performance_script = performance._performance_script


def _rule_count(table: str, chain: str) -> str:
    return (
        f'$(iptables -w 5 -t {shlex.quote(table)} -S {shlex.quote(chain)} '
        "2>/dev/null | grep -c '^-A ')"
    )


def _egress_stability_guard(subnets: list[str]) -> str:
    expected_egress = len(subnets)
    expected_fwd = len(subnets) * 2
    expected_mss = len(subnets)

    checks: list[str] = []

    for subnet in subnets:
        q = shlex.quote(subnet)

        checks.extend(
            [
                (
                    "ipt -t nat -C TP_ACCESS_EGRESS "
                    f"-s {q} -o \"$WAN\" -j MASQUERADE "
                    "2>/dev/null || STABLE=0"
                ),
                (
                    "ipt -t filter -C TP_ACCESS_FWD "
                    f"-s {q} -o \"$WAN\" -j ACCEPT "
                    "2>/dev/null || STABLE=0"
                ),
                (
                    "ipt -t filter -C TP_ACCESS_FWD "
                    f"-d {q} -i \"$WAN\" "
                    "-m conntrack --ctstate ESTABLISHED,RELATED "
                    "-j ACCEPT 2>/dev/null || STABLE=0"
                ),
                (
                    "ipt -t mangle -C TP_ACCESS_MSS "
                    f"-s {q} -o \"$WAN\" -p tcp "
                    "--tcp-flags SYN,RST SYN "
                    "-j TCPMSS --clamp-mss-to-pmtu "
                    "2>/dev/null || STABLE=0"
                ),
            ]
        )

    check_block = "\n".join(checks)

    return f"""
set -e

WAN="$(ip -o -4 route show default | awk '{{for(i=1;i<=NF;i++) if($i==\"dev\"){{print $(i+1); exit}}}}')"
[ -n "$WAN" ]
ip link show dev "$WAN" >/dev/null 2>&1

ipt() {{ iptables -w 5 "$@"; }}
STABLE=1

[ "$(sysctl -n net.ipv4.ip_forward 2>/dev/null || echo 0)" = "1" ] || STABLE=0

ipt -t nat -S TP_ACCESS_EGRESS >/dev/null 2>&1 || STABLE=0
ipt -t filter -S TP_ACCESS_FWD >/dev/null 2>&1 || STABLE=0
ipt -t mangle -S TP_ACCESS_MSS >/dev/null 2>&1 || STABLE=0

ipt -t nat -C POSTROUTING -j TP_ACCESS_EGRESS 2>/dev/null || STABLE=0
ipt -t filter -C FORWARD -j TP_ACCESS_FWD 2>/dev/null || STABLE=0
ipt -t mangle -C FORWARD -j TP_ACCESS_MSS 2>/dev/null || STABLE=0

[ "{_rule_count('nat', 'TP_ACCESS_EGRESS')}" -eq {expected_egress} ] || STABLE=0
[ "{_rule_count('filter', 'TP_ACCESS_FWD')}" -eq {expected_fwd} ] || STABLE=0
[ "{_rule_count('mangle', 'TP_ACCESS_MSS')}" -eq {expected_mss} ] || STABLE=0

{check_block}

if [ "$STABLE" -eq 1 ]; then
  echo "{MARKER}_V46_STABLE=1"
  echo "WAN=$WAN"
  ipt -t nat -S TP_ACCESS_EGRESS
  ipt -t filter -S TP_ACCESS_FWD
  exit 0
fi
""".strip()


def _egress_script_v144(subnets: list[str]) -> str:
    return (
        _egress_stability_guard(subnets)
        + "\n\n# V144 drift fallback: existing V46 repair path\n"
        + _original_egress_script(subnets)
    )


def _performance_stability_guard() -> str:
    checks: list[str] = []

    for subnet in performance._PROTOCOL_SUBNETS:
        q = shlex.quote(subnet)
        checks.extend(
            [
                (
                    "ipt -t mangle -C TP_ACCESS_PERF "
                    f"-s {q} -o \"$WAN\" -p tcp "
                    "--tcp-flags SYN,RST SYN "
                    f"-j TCPMSS --set-mss {int(performance.ACCESS_TCP_MSS)} "
                    "2>/dev/null || STABLE=0"
                ),
                (
                    "ipt -t mangle -C TP_ACCESS_PERF "
                    f"-d {q} -i \"$WAN\" -p tcp "
                    "--tcp-flags SYN,RST SYN "
                    f"-j TCPMSS --set-mss {int(performance.ACCESS_TCP_MSS)} "
                    "2>/dev/null || STABLE=0"
                ),
            ]
        )

    check_block = "\n".join(checks)
    expected_rules = len(performance._PROTOCOL_SUBNETS) * 2

    return f"""
set -e

ACCESS_MTU={int(performance.ACCESS_MTU)}
ACCESS_MSS={int(performance.ACCESS_TCP_MSS)}
WAN="$(ip -o -4 route show default | awk '{{for(i=1;i<=NF;i++) if($i==\"dev\"){{print $(i+1); exit}}}}')"
[ -n "$WAN" ]
ip link show dev "$WAN" >/dev/null 2>&1

ipt() {{ iptables -w 5 "$@"; }}
STABLE=1

[ "$(sysctl -n net.ipv4.ip_forward 2>/dev/null || echo 0)" = "1" ] || STABLE=0
[ "$(sysctl -n net.ipv4.tcp_mtu_probing 2>/dev/null || echo 0)" = "1" ] || STABLE=0

ipt -t mangle -S TP_ACCESS_PERF >/dev/null 2>&1 || STABLE=0
ipt -t mangle -C FORWARD -j TP_ACCESS_PERF 2>/dev/null || STABLE=0
[ "{_rule_count('mangle', 'TP_ACCESS_PERF')}" -eq {expected_rules} ] || STABLE=0

{check_block}

if [ -f /etc/ocserv/ocserv.conf ]; then
  grep -Eq '^[[:space:]]*mtu[[:space:]]*=[[:space:]]*1200[[:space:]]*$'     /etc/ocserv/ocserv.conf || STABLE=0
fi

if [ -f /etc/openvpn/server/twinpanel.conf ]; then
  grep -Eq '^[[:space:]]*tun-mtu[[:space:]]+1200[[:space:]]*$'     /etc/openvpn/server/twinpanel.conf || STABLE=0
  grep -Eq '^[[:space:]]*mssfix[[:space:]]+1160[[:space:]]*$'     /etc/openvpn/server/twinpanel.conf || STABLE=0
fi

if [ -f /etc/wireguard/wg-access0.conf ]; then
  grep -Eq '^[[:space:]]*MTU[[:space:]]*=[[:space:]]*1200[[:space:]]*$'     /etc/wireguard/wg-access0.conf || STABLE=0
fi

if [ -f /etc/ppp/options.xl2tpd ]; then
  grep -Eq '^[[:space:]]*mtu[[:space:]]+1200[[:space:]]*$'     /etc/ppp/options.xl2tpd || STABLE=0
  grep -Eq '^[[:space:]]*mru[[:space:]]+1200[[:space:]]*$'     /etc/ppp/options.xl2tpd || STABLE=0
fi

for IFACE in $(ls /sys/class/net 2>/dev/null | grep '^vpns' || true); do
  [ "$(cat /sys/class/net/$IFACE/mtu 2>/dev/null || echo 0)" = "$ACCESS_MTU" ]     || STABLE=0
done

OVPN_IF="$(ip -o -4 addr show | awk 'index($4,\"10.92.0.1/\")==1 {{print $2; exit}}')"
if [ -n "$OVPN_IF" ]; then
  [ "$(cat /sys/class/net/$OVPN_IF/mtu 2>/dev/null || echo 0)" = "$ACCESS_MTU" ]     || STABLE=0
fi

if ip link show wg-access0 >/dev/null 2>&1; then
  [ "$(cat /sys/class/net/wg-access0/mtu 2>/dev/null || echo 0)" = "$ACCESS_MTU" ]     || STABLE=0
fi

if [ "$STABLE" -eq 1 ]; then
  echo "V51_OK=1"
  echo "WAN=$WAN"
  echo "ACCESS_MTU=$ACCESS_MTU"
  echo "ACCESS_MSS=$ACCESS_MSS"
  echo "{MARKER}_V51_STABLE=1"
  ipt -t mangle -S TP_ACCESS_PERF
  exit 0
fi
""".strip()


def _performance_script_v144() -> str:
    return (
        _performance_stability_guard()
        + "\n\n# V144 drift fallback: existing V51 repair path\n"
        + _original_performance_script()
    )


def apply_exit_access_dataplane_stability_v144() -> None:
    global _applied

    if _applied:
        return

    dataplane._egress_script = _egress_script_v144
    performance._performance_script = _performance_script_v144

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "steady_state=read-only "
        "v46=guarded "
        "v51=guarded "
        "drift_fallback=existing-repair",
        flush=True,
    )
