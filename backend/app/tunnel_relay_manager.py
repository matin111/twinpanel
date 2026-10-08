# TWINPANEL_GENERIC_RELAY_MANAGER_V61
from __future__ import annotations

import asyncio
from datetime import datetime

from .database import SessionLocal
from .models import Node, Tunnel, TunnelStatus, TunnelTransport
from .ssh_relay import (
    choose_relay_node,
    provision_ssh_relay,
    relay_config,
    verify_ssh_relay,
)
from .ssh_tunnel import ssh_tunnel_health_meta, ssh_tunnel_interface

LOOP_SECONDS = 8
FAIL_THRESHOLD = 2
FAILBACK_SECONDS = 35

_fail_counts: dict[int, int] = {}
_primary_healthy_since: dict[int, float | None] = {}


def _member(db, tunnel_id: int, name: str):
    return (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == name,
        )
        .first()
    )


def _ensure_member(db, tunnel_id: int, name: str, priority: int):
    row = _member(db, tunnel_id, name)
    if not row:
        row = TunnelTransport(
            tunnel_id=int(tunnel_id),
            transport=name,
            priority=int(priority),
            enabled=False,
            status="not_installed",
        )
        db.add(row)
        db.flush()
    return row


async def _primary_health(tunnel, iran, db) -> dict:
    from .routers.provision import ssh_connect_saved

    peer_ip, service = ssh_tunnel_health_meta(
        tunnel,
        int(iran.id),
    )
    iface = ssh_tunnel_interface(tunnel)
    if not peer_ip or not service:
        return {"ok": False, "latency_ms": None, "error": "primary_health_meta_missing"}

    conn = None
    try:
        conn = await ssh_connect_saved(iran, db)
        result = await conn.run(
            f"""
set -e
systemctl is-active --quiet {service}
LC_ALL=C ping -I {iface} -c 3 -i 0.20 -W 2 -s 900 {peer_ip}
""",
            check=False,
            timeout=20,
        )
        if result.exit_status != 0:
            return {
                "ok": False,
                "latency_ms": None,
                "error": (result.stderr or result.stdout or "primary_probe_failed")[-700:],
            }
        latency = None
        for line in result.stdout.splitlines():
            if "min/avg/max" in line and "=" in line:
                try:
                    latency = int(float(line.split("=", 1)[1].strip().split("/")[1]))
                except Exception:
                    pass
        return {"ok": True, "latency_ms": latency, "error": None}
    except Exception as exc:
        return {"ok": False, "latency_ms": None, "error": str(exc)[:700]}
    finally:
        if conn:
            conn.close()
            await conn.wait_closed()


async def _relay_health(tunnel, iran, db) -> dict:
    try:
        result = await verify_ssh_relay(tunnel, iran, db)
        return {
            "ok": True,
            "latency_ms": result.get("latency_ms"),
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "latency_ms": None, "error": str(exc)[:700]}


async def _ensure_relay(tunnel_id: int):
    db = SessionLocal()
    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if not tunnel or not tunnel.is_active:
            return
        if str(tunnel.transport or "").strip().lower() != "ssh_tun":
            return

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if not iran or not exit_node:
            return

        primary = _ensure_member(db, tunnel.id, "ssh_tun", 100)
        primary.enabled = True
        if primary.status == "not_installed":
            primary.status = "online" if tunnel.status == TunnelStatus.ONLINE else "offline"

        relay = _ensure_member(db, tunnel.id, "ssh_relay", 200)
        db.commit()

        cfg = relay_config(db, tunnel)
        if cfg:
            health = await _relay_health(tunnel, iran, db)
            if health["ok"]:
                relay = _member(db, tunnel.id, "ssh_relay")
                relay.enabled = True
                relay.status = "online"
                relay.latency_ms = health["latency_ms"]
                relay.last_error = None
                relay.last_healthy_at = datetime.utcnow()
                relay.updated_at = datetime.utcnow()
                tunnel.mode = "auto"
                tunnel.preferred_transport = "ssh_tun"
                if tunnel.active_transport not in {"ssh_tun", "ssh_relay"}:
                    tunnel.active_transport = "ssh_tun"
                db.commit()
                return

        relay_node = choose_relay_node(db, tunnel)
        if not relay_node:
            relay = _member(db, tunnel.id, "ssh_relay")
            relay.enabled = False
            relay.status = "not_installed"
            relay.last_error = "no_online_alternate_exit"
            relay.updated_at = datetime.utcnow()
            tunnel.mode = "manual"
            tunnel.preferred_transport = "ssh_tun"
            tunnel.active_transport = "ssh_tun"
            db.commit()
            return

        print(
            f"[RelayManager] provision tunnel={tunnel.id} relay={relay_node.id} target={exit_node.id}",
            flush=True,
        )
        await provision_ssh_relay(
            tunnel,
            iran,
            relay_node,
            exit_node,
            db,
        )
        db.refresh(tunnel)
        tunnel.mode = "auto"
        tunnel.preferred_transport = "ssh_tun"
        if tunnel.active_transport not in {"ssh_tun", "ssh_relay"}:
            tunnel.active_transport = "ssh_tun"
        db.commit()
        print(f"[RelayManager] relay ready tunnel={tunnel.id}", flush=True)
    except Exception as exc:
        print(
            f"[RelayManager] ensure relay failed tunnel={tunnel_id}: {exc!r}",
            flush=True,
        )
        db.rollback()
    finally:
        db.close()


async def _manage_one(tunnel_id: int):
    db = SessionLocal()
    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if not tunnel or not tunnel.is_active:
            return
        if str(tunnel.transport or "").strip().lower() != "ssh_tun":
            return

        iran = db.get(Node, int(tunnel.iran_node_id))
        if not iran:
            return

        primary_row = _ensure_member(db, tunnel.id, "ssh_tun", 100)
        relay_row = _ensure_member(db, tunnel.id, "ssh_relay", 200)
        db.commit()

        if not relay_row.enabled or relay_row.status == "not_installed":
            return

        primary = await _primary_health(tunnel, iran, db)
        relay = await _relay_health(tunnel, iran, db)

        primary_row = _member(db, tunnel.id, "ssh_tun")
        relay_row = _member(db, tunnel.id, "ssh_relay")

        primary_row.enabled = True
        primary_row.status = "online" if primary["ok"] else "offline"
        primary_row.latency_ms = primary["latency_ms"]
        primary_row.last_error = primary["error"]
        if primary["ok"]:
            primary_row.last_healthy_at = datetime.utcnow()

        relay_row.enabled = True
        relay_row.status = "online" if relay["ok"] else "offline"
        relay_row.latency_ms = relay["latency_ms"]
        relay_row.last_error = relay["error"]
        if relay["ok"]:
            relay_row.last_healthy_at = datetime.utcnow()

        now_loop = asyncio.get_running_loop().time()
        tid = int(tunnel.id)
        active = str(tunnel.active_transport or "ssh_tun")

        if primary["ok"]:
            _fail_counts[tid] = 0
            if _primary_healthy_since.get(tid) is None:
                _primary_healthy_since[tid] = now_loop
        else:
            _fail_counts[tid] = _fail_counts.get(tid, 0) + 1
            _primary_healthy_since[tid] = None

        switched = False

        if active == "ssh_tun":
            if (
                not primary["ok"]
                and relay["ok"]
                and _fail_counts.get(tid, 0) >= FAIL_THRESHOLD
            ):
                tunnel.active_transport = "ssh_relay"
                tunnel.last_switch_at = datetime.utcnow()
                active = "ssh_relay"
                switched = True
                print(
                    f"[RelayManager] FAILOVER tunnel={tid} ssh_tun -> ssh_relay",
                    flush=True,
                )
        else:
            if not relay["ok"] and primary["ok"]:
                tunnel.active_transport = "ssh_tun"
                tunnel.last_switch_at = datetime.utcnow()
                active = "ssh_tun"
                switched = True
                print(
                    f"[RelayManager] FAILBACK tunnel={tid} relay_failed -> ssh_tun",
                    flush=True,
                )
            elif primary["ok"]:
                healthy_since = _primary_healthy_since.get(tid)
                if healthy_since is not None and (now_loop - healthy_since) >= FAILBACK_SECONDS:
                    tunnel.active_transport = "ssh_tun"
                    tunnel.last_switch_at = datetime.utcnow()
                    active = "ssh_tun"
                    switched = True
                    print(
                        f"[RelayManager] FAILBACK tunnel={tid} preferred ssh_tun stable",
                        flush=True,
                    )

        active_ok = primary["ok"] if active == "ssh_tun" else relay["ok"]
        alternate_ok = relay["ok"] if active == "ssh_tun" else primary["ok"]

        if active_ok:
            tunnel.status = TunnelStatus.ONLINE
        elif alternate_ok:
            tunnel.status = TunnelStatus.DEGRADED
        else:
            tunnel.status = TunnelStatus.OFFLINE

        tunnel.latency_ms = (
            primary["latency_ms"] if active == "ssh_tun" else relay["latency_ms"]
        )
        tunnel.mode = "auto"
        tunnel.preferred_transport = "ssh_tun"
        db.commit()

        if switched:
            await asyncio.sleep(1)
    except Exception as exc:
        print(
            f"[RelayManager] manage failed tunnel={tunnel_id}: {exc!r}",
            flush=True,
        )
        db.rollback()
    finally:
        db.close()


async def cycle():
    db = SessionLocal()
    try:
        ids = [
            int(t.id)
            for t in (
                db.query(Tunnel)
                .filter(Tunnel.is_active.is_(True))
                .order_by(Tunnel.id.asc())
                .all()
            )
            if str(t.transport or "").strip().lower() == "ssh_tun"
        ]
    finally:
        db.close()

    for tid in ids:
        await _ensure_relay(tid)
    for tid in ids:
        await _manage_one(tid)


async def main():
    print("TWINPANEL_RELAY_MANAGER_V61_START", flush=True)
    while True:
        try:
            await cycle()
        except Exception as exc:
            print("[RelayManager] cycle error", repr(exc), flush=True)
        await asyncio.sleep(LOOP_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
