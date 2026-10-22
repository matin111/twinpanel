from __future__ import annotations

import asyncio
import re
import shlex

from . import common as candidate_common
from . import tp27_fast, tp27_masque, tp27_tcp_direct


# ============================================================
# TWINPANEL CORE CANDIDATE RUNTIME V179
#
# Process-invariant candidate dataplane policy.
#
# Previous qualification fixes were applied only from the transport-manager
# process. FastAPI canary actions import transport_candidates independently,
# so the panel continued to execute the raw legacy probe / MASQUE startup path.
# This module is applied by transport_candidates.__init__ itself, making the
# same contract authoritative in API, workers and the transport manager.
# ============================================================

MARKER = "TWINPANEL_CORE_CANDIDATE_RUNTIME_V179"
TCP_EGRESS_TARGETS = (
    ("1.1.1.1", 443),
    ("1.0.0.1", 443),
    ("8.8.8.8", 443),
)

_applied = False
_original_masque_install_profile = tp27_masque._install_profile


def _clean_detail(value: str, limit: int = 1200) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[-limit:] if text else "no_detail"


async def probe_v179(
    ci,
    ce,
    *,
    name: str,
    tunnel_id: int,
    rt: dict,
) -> dict:
    """Full L3 probe used identically by API canaries and SmartAuto."""

    table, priority = candidate_common.policy_ids(name, tunnel_id)
    public_if = await candidate_common.default_interface(ce)
    comment = f"TwinPanel-{name}-{int(tunnel_id)}"
    iface = str(rt["interface"])
    network = str(rt["network"])
    iran_ip = str(rt["iran_ip"])
    exit_ip = str(rt["exit_ip"])

    await candidate_common.run(
        ce,
        f"""
set -e
sysctl -w net.ipv4.ip_forward=1 >/dev/null
if [ -e /proc/sys/net/ipv4/conf/{iface}/rp_filter ]; then
  sysctl -w net.ipv4.conf.{iface}.rp_filter=2 >/dev/null
fi
if command -v iptables >/dev/null 2>&1; then
  iptables -t nat -C POSTROUTING \
    -s {shlex.quote(network)} -o {shlex.quote(public_if)} \
    -m comment --comment {shlex.quote(comment)} -j MASQUERADE 2>/dev/null || \
  iptables -t nat -A POSTROUTING \
    -s {shlex.quote(network)} -o {shlex.quote(public_if)} \
    -m comment --comment {shlex.quote(comment)} -j MASQUERADE

  iptables -C FORWARD -i {shlex.quote(iface)} -o {shlex.quote(public_if)} \
    -s {shlex.quote(network)} -m comment --comment {shlex.quote(comment)} \
    -j ACCEPT 2>/dev/null || \
  iptables -I FORWARD -i {shlex.quote(iface)} -o {shlex.quote(public_if)} \
    -s {shlex.quote(network)} -m comment --comment {shlex.quote(comment)} \
    -j ACCEPT

  iptables -C FORWARD -i {shlex.quote(public_if)} -o {shlex.quote(iface)} \
    -d {shlex.quote(network)} -m conntrack --ctstate ESTABLISHED,RELATED \
    -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null || \
  iptables -I FORWARD -i {shlex.quote(public_if)} -o {shlex.quote(iface)} \
    -d {shlex.quote(network)} -m conntrack --ctstate ESTABLISHED,RELATED \
    -m comment --comment {shlex.quote(comment)} -j ACCEPT
fi
""",
        "canary_exit_dataplane_v179",
        45,
    )

    await candidate_common.run(
        ci,
        f"""
set -e
if [ -e /proc/sys/net/ipv4/conf/{iface}/rp_filter ]; then
  sysctl -w net.ipv4.conf.{iface}.rp_filter=2 >/dev/null
fi
ip rule del priority {int(priority)} 2>/dev/null || true
ip route flush table {int(table)} 2>/dev/null || true
ip route add table {int(table)} default via {shlex.quote(exit_ip)} dev {shlex.quote(iface)}
ip rule add priority {int(priority)} from {shlex.quote(iran_ip)}/32 table {int(table)}
""",
        "canary_iran_policy_v179",
        45,
    )

    p1, p2 = await asyncio.gather(
        ci.run(
            f"LC_ALL=C ping -I {shlex.quote(iface)} -c 3 -W 2 {shlex.quote(exit_ip)}",
            check=False,
            timeout=15,
        ),
        ce.run(
            f"LC_ALL=C ping -I {shlex.quote(iface)} -c 3 -W 2 {shlex.quote(iran_ip)}",
            check=False,
            timeout=15,
        ),
    )

    iran_loss = candidate_common.parse_packet_loss_pct(p1.stdout or "")
    exit_loss = candidate_common.parse_packet_loss_pct(p2.stdout or "")
    if iran_loss is None or exit_loss is None:
        raise RuntimeError(
            "peer_ping_loss_parse_failed:"
            f"iran={iran_loss!r}:exit={exit_loss!r}"
        )
    if p1.exit_status != 0 or p2.exit_status != 0:
        raise RuntimeError(
            "peer_ping_failed:"
            f"iran={p1.exit_status}/{iran_loss:.1f}%:"
            f"exit={p2.exit_status}/{exit_loss:.1f}%"
        )

    packet_loss = max(float(iran_loss), float(exit_loss))
    iran_rtt = candidate_common.parse_ping_rtt(p1.stdout or "")
    exit_rtt = candidate_common.parse_ping_rtt(p2.stdout or "")
    latency = None if iran_rtt is None else max(1, int(round(float(iran_rtt[0]))))
    jitter_values = [
        float(value[1])
        for value in (iran_rtt, exit_rtt)
        if value is not None
    ]
    jitter = max(jitter_values) if jitter_values else None

    tcp = await ci.run(
        f"""python3 - <<'PY'
import socket
src={iran_ip!r}
targets={list(TCP_EGRESS_TARGETS)!r}
errors=[]
for host,port in targets:
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.settimeout(4.0)
    try:
        s.bind((src,0))
        s.connect((host,int(port)))
        print(f"TCP_OK={{host}}:{{port}}")
        raise SystemExit(0)
    except OSError as exc:
        errors.append(f"{{host}}:{{port}}={{type(exc).__name__}}:{{exc}}")
    finally:
        try: s.close()
        except Exception: pass
print("TCP_FAIL=" + " | ".join(errors))
raise SystemExit(1)
PY""",
        check=False,
        timeout=20,
    )
    if tcp.exit_status != 0:
        detail = _clean_detail((tcp.stdout or "") + " " + (tcp.stderr or ""))
        raise RuntimeError("tcp_egress_probe_failed:" + detail)

    # External public-IP services are telemetry only. They never decide health.
    public_ip = await ci.run(
        f"""
set +e
for URL in https://api.ipify.org https://ifconfig.me/ip; do
  OUT="$(curl --interface {shlex.quote(iran_ip)} -4 -fsS \
    --connect-timeout 3 --max-time 5 "$URL" 2>/dev/null)" || true
  if printf '%s' "$OUT" | grep -Eq '^[0-9]+([.][0-9]+){{3}}$'; then
    printf '%s' "$OUT"
    exit 0
  fi
done
exit 0
""",
        check=False,
        timeout=14,
    )
    egress_ip = (public_ip.stdout or "").strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", egress_ip):
        egress_ip = None

    udp = await ci.run(
        f"""python3 - <<'PY'
import random,socket,struct
src={iran_ip!r}; tid=random.randrange(65536)
q=struct.pack('!HHHHHH',tid,0x0100,1,0,0,0)
for part in 'cloudflare.com'.split('.'):
    q+=bytes([len(part)])+part.encode()
q+=b'\\x00'+struct.pack('!HH',1,1)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.settimeout(5)
s.bind((src,0))
s.sendto(q,('1.1.1.1',53))
data,_=s.recvfrom(4096)
raise SystemExit(0 if len(data)>=12 and struct.unpack('!H',data[:2])[0]==tid else 2)
PY""",
        check=False,
        timeout=12,
    )
    if udp.exit_status != 0:
        detail = _clean_detail((udp.stdout or "") + " " + (udp.stderr or ""))
        raise RuntimeError("udp_egress_probe_failed:" + detail)

    return {
        "peer_ping": True,
        "tcp_egress": True,
        "udp_egress": True,
        "egress_ip": egress_ip,
        "tcp_probe": (tcp.stdout or "").strip(),
        "latency_ms": latency,
        "jitter_ms": jitter,
        "packet_loss_pct": packet_loss,
        "iran_packet_loss_pct": float(iran_loss),
        "exit_packet_loss_pct": float(exit_loss),
        "iran_jitter_ms": None if iran_rtt is None else float(iran_rtt[1]),
        "exit_jitter_ms": None if exit_rtt is None else float(exit_rtt[1]),
    }


async def _wait_current_service_marker(
    conn,
    *,
    service: str,
    marker: str,
    label: str,
    attempts: int = 56,
) -> None:
    result = await conn.run(
        f"""
set +e
for i in $(seq 1 {int(attempts)}); do
  if ! systemctl is-active --quiet {shlex.quote(service)}; then
    echo SERVICE_INACTIVE
    systemctl status {shlex.quote(service)} --no-pager -l 2>&1 || true
    exit 2
  fi
  pid="$(systemctl show {shlex.quote(service)} -p MainPID --value 2>/dev/null)"
  if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    if journalctl "_PID=$pid" -n 160 --no-pager 2>/dev/null | grep -Fq {shlex.quote(marker)}; then
      echo "READY pid=$pid marker={marker}"
      exit 0
    fi
  fi
  sleep 0.25
done
pid="$(systemctl show {shlex.quote(service)} -p MainPID --value 2>/dev/null)"
echo "TIMEOUT pid=$pid marker={marker}"
if [ -n "$pid" ] && [ "$pid" != "0" ]; then
  journalctl "_PID=$pid" -n 160 --no-pager 2>&1 || true
else
  journalctl -u {shlex.quote(service)} -n 160 --no-pager 2>&1 || true
fi
exit 1
""",
        check=False,
        timeout=28,
    )
    if result.exit_status != 0:
        detail = _clean_detail((result.stdout or "") + " " + (result.stderr or ""), 1600)
        raise RuntimeError(f"masque_session_not_ready:{label}:{detail}")


async def masque_install_profile_ready_v179(ci, ce, **kwargs) -> None:
    await _original_masque_install_profile(ci, ce, **kwargs)
    rt = kwargs["rt"]
    await asyncio.gather(
        _wait_current_service_marker(
            ci,
            service=str(rt["iran_service"]),
            marker="TP27_MASQUE_CLIENT_READY",
            label="iran_client",
        ),
        _wait_current_service_marker(
            ce,
            service=str(rt["exit_service"]),
            marker="TP27_MASQUE_SESSION_UP",
            label="exit_server",
        ),
    )


def apply_core_candidate_runtime_v179() -> None:
    global _applied
    if _applied:
        return

    # Every import of app.transport_candidates, including FastAPI canaries,
    # receives the same probe contract. Candidate modules imported probe via
    # `from .common import probe`, so update those aliases explicitly too.
    candidate_common.probe = probe_v179
    tp27_fast.probe = probe_v179
    tp27_masque.probe = probe_v179
    tp27_tcp_direct.probe = probe_v179
    tp27_masque._install_profile = masque_install_profile_ready_v179

    _applied = True
