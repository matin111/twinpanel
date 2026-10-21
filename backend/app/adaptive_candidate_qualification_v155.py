from __future__ import annotations

import asyncio
import shlex
import time
from datetime import datetime

from . import smart_transport_auto_v21 as smart
from .database import SessionLocal
from .models import Node, TunnelTransport
from .transport_candidates import common
from .transport_candidates import tp27_tcp_direct


# ============================================================
# TWINPANEL ADAPTIVE CANDIDATE QUALIFICATION V155
#
# Production evidence on Tunnel #5 proved that TP27 Direct TCP can establish
# all outer TCP lanes and carry peer-L3 packets while the generic candidate
# probe still rejects the carrier on synthetic public-Internet egress. A
# transport carrier is responsible for Iran <-> Exit L3 delivery; public
# Internet egress of the carrier /30 is not part of the production VPN service
# path and must not be a hard install/health gate.
#
# V155 therefore:
#   * keeps TP27 Fast unchanged;
#   * qualifies TP27 Direct TCP on peer L3 loss/latency;
#   * keeps public TCP/UDP egress as advisory telemetry only;
#   * keeps SmartAuto's 60s stability + bidirectional throughput benchmark as
#     the promotion gate;
#   * keeps MASQUE strict because its outer path is UDP-dependent;
#   * shortens retry only for the two warm standby lanes.
# ============================================================

MARKER = "TWINPANEL_ADAPTIVE_CANDIDATE_QUALIFICATION_V155"
DIRECT = "tp27_tcp_direct"
MASQUE = "tp27_masque"
WARM_RETRY_SECONDS = 120.0

_applied = False
_original_candidate_health = smart.candidate_health_remote_v21


async def _direct_peer_l3_probe(ci, ce, *, name: str, tunnel_id: int, rt: dict) -> dict:
    """Hard-gate Direct TCP on peer L3; keep Internet egress advisory."""
    table, priority = common.policy_ids(name, tunnel_id)
    public_if = await common.default_interface(ce)
    comment = f"TwinPanel-{name}-{int(tunnel_id)}"

    await common.run(
        ce,
        f"""
set -e
sysctl -w net.ipv4.ip_forward=1 >/dev/null
if command -v iptables >/dev/null 2>&1; then
 iptables -t nat -C POSTROUTING -s {shlex.quote(rt['network'])} -o {shlex.quote(public_if)} -m comment --comment {shlex.quote(comment)} -j MASQUERADE 2>/dev/null || \
 iptables -t nat -A POSTROUTING -s {shlex.quote(rt['network'])} -o {shlex.quote(public_if)} -m comment --comment {shlex.quote(comment)} -j MASQUERADE
fi
""",
        "direct_canary_nat_v155",
        45,
    )

    await common.run(
        ci,
        f"""
set -e
ip rule del priority {priority} 2>/dev/null || true
ip route flush table {table} 2>/dev/null || true
ip route add table {table} default via {shlex.quote(rt['exit_ip'])} dev {shlex.quote(rt['interface'])}
ip rule add priority {priority} from {shlex.quote(rt['iran_ip'])}/32 table {table}
""",
        "direct_canary_policy_v155",
        45,
    )

    p_iran, p_exit = await asyncio.gather(
        ci.run(
            f"LC_ALL=C ping -I {shlex.quote(rt['interface'])} -c 5 -W 2 {shlex.quote(rt['exit_ip'])}",
            check=False,
            timeout=18,
        ),
        ce.run(
            f"LC_ALL=C ping -I {shlex.quote(rt['interface'])} -c 5 -W 2 {shlex.quote(rt['iran_ip'])}",
            check=False,
            timeout=18,
        ),
    )

    iran_loss = common.parse_packet_loss_pct(p_iran.stdout or "")
    exit_loss = common.parse_packet_loss_pct(p_exit.stdout or "")
    if iran_loss is None or exit_loss is None:
        raise RuntimeError(f"direct_peer_ping_loss_parse_failed:iran={iran_loss!r}:exit={exit_loss!r}")
    if p_iran.exit_status != 0 or p_exit.exit_status != 0:
        raise RuntimeError(
            "direct_peer_ping_failed:"
            f"iran={p_iran.exit_status}/{iran_loss:.1f}%:"
            f"exit={p_exit.exit_status}/{exit_loss:.1f}%"
        )

    packet_loss = max(float(iran_loss), float(exit_loss))
    iran_rtt = common.parse_ping_rtt(p_iran.stdout or "")
    exit_rtt = common.parse_ping_rtt(p_exit.stdout or "")
    latency = None if iran_rtt is None else max(1, int(round(float(iran_rtt[0]))))
    jitter_values = [float(value[1]) for value in (iran_rtt, exit_rtt) if value is not None]
    jitter = max(jitter_values) if jitter_values else None

    tcp_task = ci.run(
        f"""
set +e
for URL in https://api.ipify.org https://ifconfig.me/ip; do
 OUT="$(curl --interface {shlex.quote(rt['iran_ip'])} -4 -fsS --max-time 5 "$URL" 2>/dev/null)" || true
 if printf '%s' "$OUT" | grep -Eq '^[0-9]+([.][0-9]+){{3}}$'; then printf '%s' "$OUT"; exit 0; fi
done
exit 1
""",
        check=False,
        timeout=15,
    )
    udp_task = ci.run(
        f"""python3 - <<'PY2'
import random,socket,struct
src={rt['iran_ip']!r}; tid=random.randrange(65536)
q=struct.pack('!HHHHHH',tid,0x0100,1,0,0,0)
for part in 'cloudflare.com'.split('.'):
    q+=bytes([len(part)])+part.encode()
q+=b'\\x00'+struct.pack('!HH',1,1)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.settimeout(4)
s.bind((src,0))
s.sendto(q,('1.1.1.1',53))
data,_=s.recvfrom(4096)
raise SystemExit(0 if len(data)>=12 and struct.unpack('!H',data[:2])[0]==tid else 2)
PY2""",
        check=False,
        timeout=8,
    )
    tcp, udp = await asyncio.gather(tcp_task, udp_task)

    return {
        "peer_ping": True,
        "tcp_egress": tcp.exit_status == 0,
        "udp_egress": udp.exit_status == 0,
        "egress_ip": (tcp.stdout or "").strip() if tcp.exit_status == 0 else None,
        "latency_ms": latency,
        "jitter_ms": jitter,
        "packet_loss_pct": packet_loss,
        "iran_packet_loss_pct": float(iran_loss),
        "exit_packet_loss_pct": float(exit_loss),
        "iran_jitter_ms": None if iran_rtt is None else float(iran_rtt[1]),
        "exit_jitter_ms": None if exit_rtt is None else float(exit_rtt[1]),
        "qualification_basis": "peer_l3",
        "internet_egress_advisory": True,
    }


async def _candidate_health_v155(tunnel_id: int, name: str, cfg: dict) -> tuple[str, dict]:
    value = str(name or "").strip().lower()
    if value != DIRECT:
        return await _original_candidate_health(tunnel_id, name, cfg)

    key = (int(tunnel_id), value)
    loop = asyncio.get_running_loop()
    cached = smart._candidate_health_cache.get(key)
    if cached is not None:
        stamp, result = cached
        if loop.time() - float(stamp) < smart.HEALTH_CACHE_SECONDS:
            return value, dict(result)

    db = SessionLocal()
    ci = ce = None
    try:
        tunnel = db.get(smart.Tunnel, int(tunnel_id))
        if tunnel is None:
            raise RuntimeError("tunnel_missing")
        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if iran is None or exit_node is None:
            raise RuntimeError("node_missing")

        row = db.query(TunnelTransport).filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == value,
        ).first()
        if row is None or not row.enabled:
            raise RuntimeError("candidate_not_enabled")

        rt = smart._candidate_rt(value, int(tunnel_id))
        ci, ce = await common.connect_pair(iran, exit_node, db)

        async def local_state(conn, service: str, iface: str):
            result = await conn.run(
                "set +e\n"
                f"systemctl is-active {shlex.quote(service)} 2>/dev/null || true\n"
                f"systemctl show {shlex.quote(service)} -p NRestarts --value 2>/dev/null || echo 0\n"
                f"ip link show {shlex.quote(iface)} >/dev/null 2>&1; echo IFACE_RC=$?\n",
                check=False,
                timeout=20,
            )
            lines = (result.stdout or "").strip().splitlines()
            active = bool(lines and lines[0].strip() == "active")
            restarts = 0
            for line in lines[1:3]:
                try:
                    restarts = int(line.strip())
                    break
                except (TypeError, ValueError):
                    pass
            iface_ok = "IFACE_RC=0" in (result.stdout or "")
            return active, max(0, restarts), iface_ok

        iran_state, exit_state = await asyncio.gather(
            local_state(ci, rt["iran_service"], rt["interface"]),
            local_state(ce, rt["exit_service"], rt["interface"]),
        )
        if not iran_state[0] or not exit_state[0]:
            raise RuntimeError(f"candidate_service_inactive:iran={iran_state[0]} exit={exit_state[0]}")
        if not iran_state[2] or not exit_state[2]:
            raise RuntimeError(f"candidate_interface_missing:iran={iran_state[2]} exit={exit_state[2]}")

        health = await _direct_peer_l3_probe(ci, ce, name=value, tunnel_id=int(tunnel_id), rt=rt)
        restart_count = int(iran_state[1]) + int(exit_state[1])
        now_epoch = time.time()
        state = smart._smart_state(row)
        prior_restarts = int(state.get("restart_count", restart_count) or 0)
        stable_since = smart._safe_float(state.get("stable_since_epoch"), None)
        if stable_since is None or restart_count != prior_restarts:
            stable_since = now_epoch
        stable_seconds = max(0.0, now_epoch - float(stable_since))
        loss = smart._safe_float(health.get("packet_loss_pct"), 0.0) or 0.0

        ok = bool(health.get("peer_ping")) and loss <= smart.MAX_PACKET_LOSS_PCT
        result = {
            "ok": ok,
            "latency_ms": health.get("latency_ms"),
            "packet_loss_pct": loss,
            "restart_count": restart_count,
            "stable_seconds": stable_seconds,
            "egress_ip": health.get("egress_ip"),
            "internet_tcp_egress": bool(health.get("tcp_egress")),
            "internet_udp_egress": bool(health.get("udp_egress")),
            "qualification_basis": "peer_l3_then_throughput",
            "error": None if ok else "candidate_peer_l3_probe_failed",
        }

        smart._set_smart_state(row, merge={
            "version": 155,
            "last_probe_epoch": now_epoch,
            "last_probe_ok": bool(ok),
            "stable_since_epoch": stable_since,
            "stable_seconds": round(stable_seconds, 3),
            "restart_count": restart_count,
            "internet_tcp_egress": bool(health.get("tcp_egress")),
            "internet_udp_egress": bool(health.get("udp_egress")),
            "qualification_basis": "peer_l3_then_throughput",
            "quarantine_reason": None if ok else "peer_l3_probe_failed",
            "quarantine_until_epoch": 0.0 if ok else now_epoch + 120.0,
        })
        row.status = "online" if ok else "offline"
        row.latency_ms = result["latency_ms"] if ok else None
        row.last_error = result["error"]
        if ok:
            row.last_healthy_at = datetime.utcnow()
        db.commit()

        smart._candidate_health_cache[key] = (loop.time(), dict(result))
        return value, result

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        result = {
            "ok": False,
            "latency_ms": None,
            "packet_loss_pct": None,
            "restart_count": None,
            "stable_seconds": 0.0,
            "error": ("candidate_probe_exception:" + repr(exc))[:1400],
        }
        try:
            row = db.query(TunnelTransport).filter(
                TunnelTransport.tunnel_id == int(tunnel_id),
                TunnelTransport.transport == value,
            ).first()
            if row is not None:
                now_epoch = time.time()
                smart._set_smart_state(row, merge={
                    "version": 155,
                    "last_probe_epoch": now_epoch,
                    "last_probe_ok": False,
                    "stable_since_epoch": now_epoch,
                    "stable_seconds": 0.0,
                    "quarantine_reason": result["error"],
                    "quarantine_until_epoch": now_epoch + 120.0,
                })
                row.status = "offline"
                row.latency_ms = None
                row.last_error = result["error"]
                db.commit()
        except Exception:
            db.rollback()
        smart._candidate_health_cache[key] = (loop.time(), dict(result))
        return value, result
    finally:
        await common.close_pair(ci, ce)
        db.close()


def _install_candidate_name_v155(tunnel_id: int) -> str | None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        for name in smart.AUTO_INSTALL_NAMES:
            if name == "netrix" and not smart._netrix_available():
                continue
            row = db.query(TunnelTransport).filter(
                TunnelTransport.tunnel_id == int(tunnel_id),
                TunnelTransport.transport == name,
            ).first()
            if row is None:
                return name
            if bool(row.enabled) and smart._status(row.status) in {"online", "installing"}:
                continue
            retry_seconds = WARM_RETRY_SECONDS if name in {DIRECT, MASQUE} else smart.INSTALL_RETRY_SECONDS
            updated = getattr(row, "updated_at", None)
            if updated is not None:
                try:
                    if getattr(updated, "tzinfo", None) is not None:
                        updated = updated.replace(tzinfo=None)
                    age = max(0.0, (now - updated).total_seconds())
                    if age < retry_seconds:
                        continue
                except Exception:
                    pass
            return name
        return None
    finally:
        db.close()


def apply_adaptive_candidate_qualification_v155() -> None:
    global _applied
    if _applied:
        return
    tp27_tcp_direct.probe = _direct_peer_l3_probe
    smart.candidate_health_remote_v21 = _candidate_health_v155
    smart._install_candidate_name = _install_candidate_name_v155
    _applied = True
    print(
        f"{MARKER}_ACTIVE "
        "direct_gate=peer-l3+loss+stability+throughput "
        "internet_egress=advisory "
        "masque_gate=strict-udp "
        "warm_retry=120s "
        "tp27_fast=unchanged",
        flush=True,
    )
