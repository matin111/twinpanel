from __future__ import annotations

import asyncio
import shlex
from datetime import datetime

from .database import SessionLocal
from .models import Node, Tunnel, TunnelStatus
from .mtunnel_transport import mtunnel_runtime_values
from .routers.provision import ssh_connect_saved
from .ssh_relay import relay_addresses, relay_config
from .ssh_tunnel import ssh_tunnel_addresses
from .tunnel_transport_manager import (
    _backhaul_health,
    _backhaul_meta,
    _installed,
    _member,
    _mtunnel_health,
    _ssh_relay_health,
    _ssh_tun_health,
    _update_member,
)

# TWINPANEL_TRANSPORT_MANAGER_V6
#
# V6 keeps the V5 race fix and adds full dataplane health.
# A transport is healthy only when:
#   1) service/interface/peer probe is healthy
#   2) TCP egress bound to the transport source IP returns the target Exit IP
#   3) UDP DNS bound to the transport source IP succeeds
#
# This prevents peer-only false positives where the tunnel itself is up but
# policy routing, FORWARD or NAT is missing/broken.

LOOP_SECONDS = 5
CONFIRM_FAILURE_DELAY_SECONDS = 2
FAILBACK_SECONDS = 45

FALLBACK_ORDER = (
    "backhaul",
    "ssh_tun",
    "ssh_relay",
)

_mtunnel_healthy_since: dict[int, float | None] = {}


def _latency(health: dict) -> int | None:
    value = health.get("latency_ms")
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def _source_ip_for(name: str, tunnel, db) -> str:
    if name == "mtunnel":
        return str(
            mtunnel_runtime_values(
                int(tunnel.id)
            )["iran_ip"]
        )

    if name == "backhaul":
        return str(
            _backhaul_meta(
                int(tunnel.id)
            )["iran_ip"]
        )

    if name == "ssh_tun":
        _, iran_addr, _ = ssh_tunnel_addresses(
            tunnel
        )
        return str(iran_addr).split("/", 1)[0]

    if name == "ssh_relay":
        cfg = relay_config(
            db,
            tunnel,
        )
        if cfg.get("iran_ip"):
            return str(cfg["iran_ip"]).strip()
        _, iran_ip, _ = relay_addresses(
            tunnel
        )
        return str(iran_ip)

    raise RuntimeError(
        f"unsupported_transport_source:{name}"
    )


async def _internet_egress_health(
    *,
    name: str,
    tunnel,
    iran,
    exit_node,
    db,
    latency_ms: int | None,
) -> dict:
    source_ip = _source_ip_for(
        name,
        tunnel,
        db,
    )

    expected_exit_ip = str(
        exit_node.public_ip or ""
    ).strip()

    if not expected_exit_ip:
        return {
            "ok": False,
            "latency_ms": None,
            "error": (
                f"{name}_egress_probe_failed:"
                " exit_public_ip_missing"
            ),
        }

    conn = None

    try:
        conn = await ssh_connect_saved(
            iran,
            db,
        )

        script = f"""
set +e

SRC={shlex.quote(source_ip)}

ROUTE_TEXT="$(
  ip -4 route get 1.1.1.1 from "$SRC" 2>&1
)"
ROUTE_RC=$?

echo "TP_ROUTE_RC=$ROUTE_RC"
echo "TP_ROUTE=$ROUTE_TEXT"

TCP_IP=""

for URL in \
  https://api.ipify.org \
  https://ifconfig.me/ip
do
    TCP_IP="$(
      curl \
        --interface "$SRC" \
        -4 \
        -fsS \
        --connect-timeout 5 \
        --max-time 9 \
        "$URL" \
        2>/dev/null
    )" || true

    if printf '%s' "$TCP_IP" \
      | grep -Eq '^[0-9]+([.][0-9]+){{3}}$'
    then
        break
    fi
done

echo "TP_TCP_IP=$TCP_IP"

python3 - "$SRC" <<'PYUDP'
import random
import socket
import struct
import sys

src = sys.argv[1]
servers = (
    ("1.1.1.1", 53),
    ("8.8.8.8", 53),
)

qname = b"".join(
    bytes([len(part)]) + part.encode()
    for part in "cloudflare.com".split(".")
) + b"\\x00"

for server in servers:
    tid = random.randint(1, 65535)

    packet = (
        struct.pack(
            "!HHHHHH",
            tid,
            0x0100,
            1,
            0,
            0,
            0,
        )
        + qname
        + struct.pack("!HH", 1, 1)
    )

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    sock.settimeout(4)

    try:
        sock.bind((src, 0))
        sock.sendto(packet, server)
        data, addr = sock.recvfrom(4096)

        if len(data) < 12:
            continue

        rid = struct.unpack(
            "!H",
            data[:2],
        )[0]

        if rid != tid:
            continue

        print(
            "TP_UDP=PASS",
            addr[0],
            len(data),
        )
        raise SystemExit(0)

    except Exception as exc:
        last_error = repr(exc)

    finally:
        sock.close()

print(
    "TP_UDP=FAIL",
    locals().get("last_error", "unknown"),
)
raise SystemExit(1)
PYUDP
UDP_RC=$?

echo "TP_UDP_RC=$UDP_RC"
"""

        result = await conn.run(
            script,
            check=False,
            timeout=35,
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        tcp_ip = ""
        route_rc = None
        udp_ok = False

        for line in stdout.splitlines():
            if line.startswith("TP_TCP_IP="):
                tcp_ip = line.split("=", 1)[1].strip()
            elif line.startswith("TP_ROUTE_RC="):
                try:
                    route_rc = int(
                        line.split("=", 1)[1].strip()
                    )
                except Exception:
                    route_rc = None
            elif line.startswith("TP_UDP=PASS"):
                udp_ok = True

        problems: list[str] = []

        if route_rc != 0:
            problems.append(
                "source_route_missing"
            )

        if tcp_ip != expected_exit_ip:
            problems.append(
                "tcp_exit_ip="
                + (tcp_ip or "empty")
                + ",expected="
                + expected_exit_ip
            )

        if not udp_ok:
            problems.append(
                "udp_dns_failed"
            )

        if result.exit_status != 0 and not udp_ok:
            problems.append(
                f"probe_rc={result.exit_status}"
            )

        if problems:
            detail = (
                " | ".join(problems)
                + " | "
                + stdout[-900:]
                + " | "
                + stderr[-500:]
            )

            return {
                "ok": False,
                "latency_ms": None,
                "error": (
                    f"{name}_egress_probe_failed: "
                    + detail
                )[:1100],
            }

        return {
            "ok": True,
            "latency_ms": latency_ms,
            "error": None,
            "source_ip": source_ip,
            "egress_ip": tcp_ip,
            "udp_dns": True,
        }

    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": None,
            "error": (
                f"{name}_egress_probe_exception: "
                + str(exc)
            )[:1100],
        }

    finally:
        if conn:
            conn.close()
            await conn.wait_closed()


async def _full_health_for(
    name: str,
    tunnel,
    iran,
    exit_node,
    db,
) -> dict:
    if name == "mtunnel":
        base = await _mtunnel_health(
            tunnel,
            iran,
            exit_node,
            db,
        )

    elif name == "backhaul":
        base = await _backhaul_health(
            tunnel,
            iran,
            exit_node,
            db,
        )

    elif name == "ssh_tun":
        base = await _ssh_tun_health(
            tunnel,
            iran,
            exit_node,
            db,
        )

    elif name == "ssh_relay":
        base = await _ssh_relay_health(
            tunnel,
            iran,
            db,
        )

    else:
        return {
            "ok": False,
            "latency_ms": None,
            "error": f"unsupported_transport:{name}",
        }

    if not base.get("ok"):
        return base

    return await _internet_egress_health(
        name=name,
        tunnel=tunnel,
        iran=iran,
        exit_node=exit_node,
        db=db,
        latency_ms=_latency(base),
    )


async def _probe_fallbacks(
    tunnel,
    iran,
    exit_node,
    db,
) -> tuple[dict, str | None]:
    health: dict[str, dict] = {}
    best: str | None = None

    for name in FALLBACK_ORDER:
        row = _member(
            db,
            int(tunnel.id),
            name,
        )

        if not _installed(row):
            health[name] = {
                "ok": False,
                "latency_ms": None,
                "error": "not_installed",
            }
            continue

        result = await _full_health_for(
            name,
            tunnel,
            iran,
            exit_node,
            db,
        )

        health[name] = result

        if row:
            _update_member(
                row,
                result,
            )

        if best is None and result.get("ok"):
            best = name

    return health, best


async def _confirmed_mtunnel_health(
    tunnel,
    iran,
    exit_node,
    db,
) -> tuple[dict, bool]:
    first = await _full_health_for(
        "mtunnel",
        tunnel,
        iran,
        exit_node,
        db,
    )

    if first.get("ok"):
        return first, False

    await asyncio.sleep(
        CONFIRM_FAILURE_DELAY_SECONDS
    )

    second = await _full_health_for(
        "mtunnel",
        tunnel,
        iran,
        exit_node,
        db,
    )

    if second.get("ok"):
        return second, False

    first_error = str(
        first.get("error") or "probe1_failed"
    )

    second_error = str(
        second.get("error") or "probe2_failed"
    )

    second = dict(second)
    second["error"] = (
        "confirmed_mtunnel_failure: "
        + first_error[:360]
        + " | "
        + second_error[:360]
    )[:1100]

    return second, True


async def _manage_mtunnel_active(
    tunnel,
    iran,
    exit_node,
    db,
) -> None:
    tid = int(tunnel.id)

    mt_row = _member(
        db,
        tid,
        "mtunnel",
    )

    if not _installed(mt_row):
        mt_health = {
            "ok": False,
            "latency_ms": None,
            "error": "mtunnel_not_installed",
        }
        confirmed_failure = True
    else:
        mt_health, confirmed_failure = (
            await _confirmed_mtunnel_health(
                tunnel,
                iran,
                exit_node,
                db,
            )
        )

    if not confirmed_failure:
        if mt_row:
            _update_member(
                mt_row,
                mt_health,
            )

        tunnel.mode = "auto"
        tunnel.active_transport = "mtunnel"
        tunnel.preferred_transport = "mtunnel"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(mt_health)

        _mtunnel_healthy_since[tid] = (
            asyncio.get_running_loop().time()
        )

        db.commit()

        print(
            f"[TransportManagerV6] tunnel={tid} "
            "active=mtunnel dataplane=full status=online",
            flush=True,
        )
        return

    fallback_health, best = await _probe_fallbacks(
        tunnel,
        iran,
        exit_node,
        db,
    )

    if mt_row:
        _update_member(
            mt_row,
            mt_health,
        )

    old_active = "mtunnel"
    tunnel.mode = "auto"
    tunnel.preferred_transport = "mtunnel"
    _mtunnel_healthy_since[tid] = None

    if best:
        tunnel.active_transport = best
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(
            fallback_health[best]
        )
        tunnel.last_switch_at = datetime.utcnow()

        db.commit()

        print(
            f"[TransportManagerV6] FAILOVER tunnel={tid} "
            f"{old_active}->{best} dataplane=full status=online",
            flush=True,
        )
        return

    tunnel.status = TunnelStatus.OFFLINE
    tunnel.latency_ms = None
    db.commit()

    print(
        f"[TransportManagerV6] tunnel={tid} active=mtunnel "
        "confirmed_failed=1 fallback=none status=offline",
        flush=True,
    )


async def _manage_fallback_active(
    tunnel,
    iran,
    exit_node,
    db,
    active: str,
) -> None:
    tid = int(tunnel.id)

    active_row = _member(
        db,
        tid,
        active,
    )

    if _installed(active_row):
        active_health = await _full_health_for(
            active,
            tunnel,
            iran,
            exit_node,
            db,
        )
    else:
        active_health = {
            "ok": False,
            "latency_ms": None,
            "error": "active_fallback_not_installed",
        }

    if active_row:
        _update_member(
            active_row,
            active_health,
        )

    mt_row = _member(
        db,
        tid,
        "mtunnel",
    )

    if _installed(mt_row):
        mt_health = await _full_health_for(
            "mtunnel",
            tunnel,
            iran,
            exit_node,
            db,
        )
    else:
        mt_health = {
            "ok": False,
            "latency_ms": None,
            "error": "mtunnel_not_installed",
        }

    if mt_row:
        _update_member(
            mt_row,
            mt_health,
        )

    now = asyncio.get_running_loop().time()

    if mt_health.get("ok"):
        if _mtunnel_healthy_since.get(tid) is None:
            _mtunnel_healthy_since[tid] = now
    else:
        _mtunnel_healthy_since[tid] = None

    if not active_health.get("ok") and mt_health.get("ok"):
        tunnel.active_transport = "mtunnel"
        tunnel.preferred_transport = "mtunnel"
        tunnel.mode = "auto"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(mt_health)
        tunnel.last_switch_at = datetime.utcnow()
        db.commit()

        print(
            f"[TransportManagerV6] FAILBACK tunnel={tid} "
            f"{active}->mtunnel reason=fallback_failed dataplane=full",
            flush=True,
        )
        return

    healthy_since = _mtunnel_healthy_since.get(tid)

    if (
        active_health.get("ok")
        and mt_health.get("ok")
        and healthy_since is not None
        and (now - healthy_since) >= FAILBACK_SECONDS
    ):
        tunnel.active_transport = "mtunnel"
        tunnel.preferred_transport = "mtunnel"
        tunnel.mode = "auto"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(mt_health)
        tunnel.last_switch_at = datetime.utcnow()
        db.commit()

        print(
            f"[TransportManagerV6] FAILBACK tunnel={tid} "
            f"{active}->mtunnel stable={FAILBACK_SECONDS}s dataplane=full",
            flush=True,
        )
        return

    if active_health.get("ok"):
        tunnel.mode = "auto"
        tunnel.preferred_transport = "mtunnel"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(active_health)
        db.commit()

        print(
            f"[TransportManagerV6] tunnel={tid} "
            f"active={active} dataplane=full status=online",
            flush=True,
        )
        return

    fallback_health, best = await _probe_fallbacks(
        tunnel,
        iran,
        exit_node,
        db,
    )

    if best:
        old_active = active
        tunnel.active_transport = best
        tunnel.preferred_transport = "mtunnel"
        tunnel.mode = "auto"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = _latency(
            fallback_health[best]
        )
        tunnel.last_switch_at = datetime.utcnow()
        db.commit()

        print(
            f"[TransportManagerV6] FAILOVER tunnel={tid} "
            f"{old_active}->{best} dataplane=full status=online",
            flush=True,
        )
        return

    tunnel.mode = "auto"
    tunnel.preferred_transport = "mtunnel"
    tunnel.status = TunnelStatus.OFFLINE
    tunnel.latency_ms = None
    db.commit()

    print(
        f"[TransportManagerV6] tunnel={tid} active={active} "
        "fallback=none dataplane=full status=offline",
        flush=True,
    )


async def _manage_one(tunnel_id: int) -> None:
    db = SessionLocal()

    try:
        tunnel = db.get(
            Tunnel,
            int(tunnel_id),
        )

        if not tunnel or not tunnel.is_active:
            return

        if (
            str(
                tunnel.mode or "manual"
            ).strip().lower()
            != "auto"
        ):
            return

        iran = db.get(
            Node,
            int(tunnel.iran_node_id),
        )

        exit_node = db.get(
            Node,
            int(tunnel.exit_node_id),
        )

        if not iran or not exit_node:
            return

        active = str(
            tunnel.active_transport
            or tunnel.preferred_transport
            or "mtunnel"
        ).strip().lower()

        if active == "mtunnel":
            await _manage_mtunnel_active(
                tunnel,
                iran,
                exit_node,
                db,
            )
            return

        if active in FALLBACK_ORDER:
            await _manage_fallback_active(
                tunnel,
                iran,
                exit_node,
                db,
                active,
            )
            return

        print(
            f"[TransportManagerV6] tunnel={int(tunnel.id)} "
            f"unsupported_active={active}",
            flush=True,
        )

    except Exception as exc:
        db.rollback()
        print(
            f"[TransportManagerV6] ERROR tunnel={tunnel_id}: "
            f"{exc!r}",
            flush=True,
        )

    finally:
        db.close()


async def cycle() -> None:
    db = SessionLocal()

    try:
        ids = [
            int(item.id)
            for item in (
                db.query(Tunnel)
                .filter(
                    Tunnel.is_active.is_(True)
                )
                .order_by(Tunnel.id.asc())
                .all()
            )
        ]
    finally:
        db.close()

    for tunnel_id in ids:
        await _manage_one(
            tunnel_id,
        )


async def main() -> None:
    print(
        "TWINPANEL_TRANSPORT_MANAGER_V6_START",
        flush=True,
    )

    while True:
        try:
            await cycle()
        except Exception as exc:
            print(
                "[TransportManagerV6] cycle error "
                f"{exc!r}",
                flush=True,
            )

        await asyncio.sleep(
            LOOP_SECONDS
        )


if __name__ == "__main__":
    asyncio.run(main())
