# TWINPANEL_TRANSPORT_MANAGER_V4
from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime

from .database import SessionLocal
from .models import (
    Node,
    Tunnel,
    TunnelStatus,
    TunnelTransport,
)
from .routers.provision import ssh_connect_saved
from .ssh_tunnel import verify_ssh_tunnel
from .ssh_relay import verify_ssh_relay
from .mtunnel_transport import mtunnel_runtime_values


# ============================================================
# TWINPANEL BACKHAUL-FIRST TRANSPORT MANAGER V1
#
# Priority:
#
#   1) backhaul
#   2) ssh_tun
#   3) ssh_relay
#
# Backhaul is always preferred when installed and healthy.
# ============================================================


LOOP_SECONDS = 2
FAIL_THRESHOLD = 3
FAILBACK_SECONDS = 45

ORDER = (
    "backhaul",
    "ssh_tun",
    "ssh_relay",
)

PRIORITY = {
    "backhaul": 100,
    "ssh_tun": 200,
    "ssh_relay": 300,
}


_fail_counts: dict[tuple[int, str], int] = {}
_healthy_since: dict[tuple[int, str], float | None] = {}


def _member(
    db,
    tunnel_id: int,
    transport: str,
):
    return (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == transport,
        )
        .first()
    )


def _installed(row) -> bool:
    if not row:
        return False

    if not bool(row.enabled):
        return False

    if str(row.status or "").lower() == "not_installed":
        return False

    return True


def _backhaul_meta(tunnel_id: int) -> dict:
    tid = int(tunnel_id)

    slot = 10 + (tid % 230)

    return {
        "interface": f"bh{tid}",
        "iran_ip": f"10.253.{slot}.1",
        "exit_ip": f"10.253.{slot}.2",
        "service": f"twinpanel-backhaul-{tid}.service",
    }


def _extract_latency(value) -> int | None:
    if value is None:
        return None

    text = str(value)

    values = []

    for item in re.findall(
        r"time[=<]\s*([0-9]+(?:\.[0-9]+)?)\s*ms",
        text,
        flags=re.I,
    ):
        try:
            values.append(float(item))
        except Exception:
            pass

    if not values:
        return None

    return int(
        round(
            sum(values) / len(values)
        )
    )


async def _remote_probe(
    conn,
    service: str,
    interface: str,
    peer_ip: str,
) -> str:

    script = f"""
set -e

systemctl is-active {service}

ip link show {interface} >/dev/null

ip addr show dev {interface}

ping \
    -I {interface} \
    -c 3 \
    -W 2 \
    {peer_ip}
"""

    result = await conn.run(
        script,
        check=False,
    )

    if result.exit_status != 0:
        message = (
            result.stderr
            or result.stdout
            or "backhaul_probe_failed"
        )

        raise RuntimeError(
            message[-2000:]
        )

    return result.stdout or ""


# TWINPANEL_MTUNNEL_PHYSICAL_HEALTH_V1
async def _mtunnel_health(
    tunnel,
    iran,
    exit_node,
    db,
) -> dict:
    runtime = mtunnel_runtime_values(
        int(tunnel.id)
    )

    ci = None
    ce = None

    try:
        ci = await ssh_connect_saved(
            iran,
            db,
        )

        ce = await ssh_connect_saved(
            exit_node,
            db,
        )

        iran_result = await _remote_probe(
            ci,
            runtime["service"],
            runtime["interface"],
            runtime["exit_ip"],
        )

        exit_result = await _remote_probe(
            ce,
            runtime["service"],
            runtime["interface"],
            runtime["iran_ip"],
        )

        latency = _extract_latency(
            iran_result
            + "\n"
            + exit_result
        )

        return {
            "ok": True,
            "latency_ms": latency,
            "error": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": None,
            "error": (
                "mtunnel_physical_probe_failed: "
                + str(exc)
            )[:700],
        }

    finally:
        if ci:
            ci.close()
            await ci.wait_closed()

        if ce:
            ce.close()
            await ce.wait_closed()


async def _backhaul_health(
    tunnel,
    iran,
    exit_node,
    db,
) -> dict:

    meta = _backhaul_meta(
        tunnel.id
    )

    ci = None
    ce = None

    try:
        ci = await ssh_connect_saved(
            iran,
            db,
        )

        ce = await ssh_connect_saved(
            exit_node,
            db,
        )

        iran_result = await _remote_probe(
            ci,
            meta["service"],
            meta["interface"],
            meta["exit_ip"],
        )

        exit_result = await _remote_probe(
            ce,
            meta["service"],
            meta["interface"],
            meta["iran_ip"],
        )

        latency = _extract_latency(
            iran_result
            + "\n"
            + exit_result
        )

        return {
            "ok": True,
            "latency_ms": latency,
            "error": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": None,
            "error": (
                "backhaul_probe_failed: "
                + str(exc)
            )[:700],
        }

    finally:
        if ci:
            ci.close()
            await ci.wait_closed()

        if ce:
            ce.close()
            await ce.wait_closed()


async def _ssh_tun_health(
    tunnel,
    iran,
    exit_node,
    db,
) -> dict:

    try:
        result = await verify_ssh_tunnel(
            tunnel,
            iran,
            exit_node,
            db,
        )

        latency = _extract_latency(
            "\n".join(
                str(v)
                for v in result.values()
            )
        )

        return {
            "ok": True,
            "latency_ms": latency,
            "error": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": None,
            "error": (
                "ssh_tun_probe_failed: "
                + str(exc)
            )[:700],
        }


async def _ssh_relay_health(
    tunnel,
    iran,
    db,
) -> dict:

    try:
        result = await verify_ssh_relay(
            tunnel,
            iran,
            db,
        )

        latency = None

        if isinstance(result, dict):
            value = result.get(
                "latency_ms"
            )

            try:
                if value is not None:
                    latency = int(value)
            except Exception:
                latency = None

            if latency is None:
                latency = _extract_latency(
                    "\n".join(
                        str(v)
                        for v in result.values()
                    )
                )

        return {
            "ok": True,
            "latency_ms": latency,
            "error": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": None,
            "error": (
                "ssh_relay_probe_failed: "
                + str(exc)
            )[:700],
        }


def _update_member(
    row,
    health: dict,
):
    if not row:
        return

    now = datetime.utcnow()

    row.status = (
        "online"
        if health["ok"]
        else "offline"
    )

    row.latency_ms = health.get(
        "latency_ms"
    )

    row.last_error = health.get(
        "error"
    )

    if health["ok"]:
        row.last_healthy_at = now

    if hasattr(row, "updated_at"):
        row.updated_at = now


async def _manage_one(
    tunnel_id: int,
    promote_now: bool = False,
):

    db = SessionLocal()

    try:
        tunnel = db.get(
            Tunnel,
            int(tunnel_id),
        )

        if (
            not tunnel
            or not tunnel.is_active
        ):
            return

        # TWINPANEL_MANUAL_MANAGER_GUARD_V1
        #
        # Manual mode is authoritative.
        # Admin-selected transport must never be replaced by
        # automatic failover/failback logic.
        if (
            str(
                getattr(
                    tunnel,
                    "mode",
                    "auto",
                )
                or "auto"
            )
            .strip()
            .lower()
            == "manual"
        ):
            selected_name = str(
                tunnel.active_transport
                or tunnel.preferred_transport
                or ""
            ).strip().lower()

            allowed_manual = {
                "mtunnel",
                "backhaul",
                "ssh_tun",
            }

            if selected_name not in allowed_manual:
                tunnel.status = TunnelStatus.OFFLINE
                tunnel.latency_ms = None

                db.commit()

                print(
                    (
                        "[TransportManager] "
                        f"tunnel={int(tunnel.id)} "
                        "mode=manual "
                        "selected=invalid "
                        "status=offline"
                    ),
                    flush=True,
                )

                return

            # TWINPANEL_MANUAL_PHYSICAL_HEALTH_V2
            #
            # Manual mode keeps the admin-selected transport
            # authoritative, but status must come from a real
            # dataplane probe, never from stale DB telemetry.

            selected_row = _member(
                db,
                int(tunnel.id),
                selected_name,
            )

            iran = db.get(
                Node,
                int(tunnel.iran_node_id),
            )

            exit_node = db.get(
                Node,
                int(tunnel.exit_node_id),
            )

            if (
                not iran
                or not exit_node
            ):
                selected_health = {
                    "ok": False,
                    "latency_ms": None,
                    "error": "nodes_missing",
                }

            elif not _installed(
                selected_row
            ):
                selected_health = {
                    "ok": False,
                    "latency_ms": None,
                    "error": "not_installed",
                }

            elif selected_name == "mtunnel":
                selected_health = (
                    await _mtunnel_health(
                        tunnel,
                        iran,
                        exit_node,
                        db,
                    )
                )

            elif selected_name == "backhaul":
                selected_health = (
                    await _backhaul_health(
                        tunnel,
                        iran,
                        exit_node,
                        db,
                    )
                )

            elif selected_name == "ssh_tun":
                selected_health = (
                    await _ssh_tun_health(
                        tunnel,
                        iran,
                        exit_node,
                        db,
                    )
                )

            else:
                selected_health = {
                    "ok": False,
                    "latency_ms": None,
                    "error": (
                        "unsupported_manual_transport"
                    ),
                }

            if selected_row:
                _update_member(
                    selected_row,
                    selected_health,
                )

            if selected_health["ok"]:
                tunnel.status = (
                    TunnelStatus.ONLINE
                )
                tunnel.latency_ms = (
                    selected_health.get(
                        "latency_ms"
                    )
                )
            else:
                tunnel.status = (
                    TunnelStatus.OFFLINE
                )
                tunnel.latency_ms = None

            # IMPORTANT:
            # Do NOT change:
            #   tunnel.mode
            #   tunnel.active_transport
            #   tunnel.preferred_transport
            #   tunnel.last_switch_at
            #
            # Admin selection stays authoritative.

            db.commit()

            print(
                (
                    "[TransportManager] "
                    f"tunnel={int(tunnel.id)} "
                    "mode=manual "
                    f"active={selected_name} "
                    f"status={getattr(tunnel.status, 'value', tunnel.status)}"
                ),
                flush=True,
            )

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

        # TWINPANEL_MTUNNEL_MANAGER_AUTHORITY_V2
        #
        # MTunnel health is physical dataplane health.
        # TunnelTransport.status is telemetry only and MUST NOT
        # be used as the source of truth.
        mtunnel_row = _member(
            db,
            tunnel.id,
            "mtunnel",
        )

        mtunnel_installed = (
            _installed(mtunnel_row)
        )

        if mtunnel_installed:
            mtunnel_health = (
                await _mtunnel_health(
                    tunnel,
                    iran,
                    exit_node,
                    db,
                )
            )
        else:
            mtunnel_health = {
                "ok": False,
                "latency_ms": None,
                "error": "not_installed",
            }

        if mtunnel_row:
            _update_member(
                mtunnel_row,
                mtunnel_health,
            )

        current_active = str(
            tunnel.active_transport
            or ""
        ).strip().lower()

        if current_active == "mtunnel":
            # TWINPANEL_TRANSPORT_MANAGER_NODE_GATE_V1
            #
            # A physical transport may only make the aggregate
            # Tunnel ONLINE when BOTH endpoint Nodes themselves
            # are currently ONLINE.
            iran_status = str(
                getattr(
                    getattr(
                        iran,
                        "status",
                        None,
                    ),
                    "value",
                    getattr(
                        iran,
                        "status",
                        "",
                    ),
                )
                or ""
            ).strip().lower()

            exit_status = str(
                getattr(
                    getattr(
                        exit_node,
                        "status",
                        None,
                    ),
                    "value",
                    getattr(
                        exit_node,
                        "status",
                        "",
                    ),
                )
                or ""
            ).strip().lower()

            # TWINPANEL_ANY_HEALTHY_TRANSPORT_ONLINE_V2
            #
            # Aggregate Tunnel state follows physical transport health.
            # Node.status may be stale and MUST NOT force a healthy
            # transport/Tunnel offline. Only explicitly retired endpoints
            # are ineligible.
            endpoints_eligible = bool(
                getattr(
                    iran,
                    "retired_at",
                    None,
                )
                is None
                and getattr(
                    exit_node,
                    "retired_at",
                    None,
                )
                is None
            )

            mtunnel_online = bool(
                mtunnel_installed
                and mtunnel_health["ok"]
                and endpoints_eligible
            )

            if not endpoints_eligible:

                # Do NOT force aggregate Tunnel OFFLINE here.
                # Continue into the remaining transport manager so another
                # eligible healthy transport may be selected.
                print(
                    (
                        "[TransportManager] "
                        f"tunnel={int(tunnel.id)} "
                        "active=mtunnel "
                        "authority=endpoint_retired "
                        "continue_failover=1 "
                        f"iran={iran_status or 'unknown'} "
                        f"exit={exit_status or 'unknown'}"
                    ),
                    flush=True,
                )

            # TWINPANEL_MTUNNEL_DEBOUNCE_V4
            tid = int(tunnel.id)
            mtunnel_failure_key = (
                tid,
                "mtunnel",
            )

            if mtunnel_online:
                _fail_counts[
                    mtunnel_failure_key
                ] = 0

                now_loop = (
                    asyncio
                    .get_running_loop()
                    .time()
                )

                if (
                    _healthy_since.get(
                        mtunnel_failure_key
                    )
                    is None
                ):
                    _healthy_since[
                        mtunnel_failure_key
                    ] = now_loop

                tunnel.status = (
                    TunnelStatus.ONLINE
                )
                tunnel.active_transport = (
                    "mtunnel"
                )
                tunnel.preferred_transport = (
                    "mtunnel"
                )
                tunnel.latency_ms = (
                    mtunnel_row.latency_ms
                )
                tunnel.mode = "auto"

                db.commit()

                print(
                    (
                        "[TransportManager] "
                        f"tunnel={tid} "
                        "active=mtunnel "
                        "status=online "
                        "authority=mtunnel "
                        "fail_count=0"
                    ),
                    flush=True,
                )

                return

            _healthy_since[
                mtunnel_failure_key
            ] = None

            _fail_counts[
                mtunnel_failure_key
            ] = (
                _fail_counts.get(
                    mtunnel_failure_key,
                    0,
                )
                + 1
            )

            mtunnel_fail_count = (
                _fail_counts[
                    mtunnel_failure_key
                ]
            )

            # Do not flap on one/two transient health failures.
            if (
                endpoints_eligible
                and mtunnel_fail_count
                < FAIL_THRESHOLD
            ):
                tunnel.status = (
                    TunnelStatus.ONLINE
                )
                tunnel.preferred_transport = (
                    "mtunnel"
                )
                tunnel.mode = "auto"

                db.commit()

                print(
                    (
                        "[TransportManager] "
                        f"tunnel={tid} "
                        "active=mtunnel "
                        "status=online "
                        "authority=debounce "
                        f"fail_count={mtunnel_fail_count}/"
                        f"{FAIL_THRESHOLD}"
                    ),
                    flush=True,
                )

                return

            print(
                (
                    "[TransportManager] "
                    f"tunnel={tid} "
                    "active=mtunnel "
                    "failover_allowed=1 "
                    f"fail_count={mtunnel_fail_count}/"
                    f"{FAIL_THRESHOLD}"
                ),
                flush=True,
            )

            # MTunnel failed enough consecutive checks.
            # Continue into Backhaul / SSH fallback selection.

        # TWINPANEL_MTUNNEL_FAILBACK_STABILITY_V4
        #
        # MTunnel remains preferred even while a fallback transport
        # is active. Fail back only after continuous stability.
        current_active = str(
            tunnel.active_transport
            or ""
        ).strip().lower()

        mtunnel_row_online = bool(
            mtunnel_installed
            and mtunnel_health["ok"]
        )

        mtunnel_key = (
            int(tunnel.id),
            "mtunnel",
        )

        now_mtunnel = (
            asyncio
            .get_running_loop()
            .time()
        )

        if mtunnel_row_online:
            if (
                _healthy_since.get(
                    mtunnel_key
                )
                is None
            ):
                _healthy_since[
                    mtunnel_key
                ] = now_mtunnel
        else:
            _healthy_since[
                mtunnel_key
            ] = None

        tunnel.preferred_transport = (
            "mtunnel"
            if mtunnel_installed
            else tunnel.preferred_transport
        )

        if (
            current_active
            and current_active != "mtunnel"
            and mtunnel_row_online
        ):
            mtunnel_since = (
                _healthy_since.get(
                    mtunnel_key
                )
            )

            if (
                mtunnel_since is not None
                and (
                    now_mtunnel
                    - mtunnel_since
                )
                >= FAILBACK_SECONDS
            ):
                old_active = current_active

                tunnel.active_transport = (
                    "mtunnel"
                )
                tunnel.preferred_transport = (
                    "mtunnel"
                )
                tunnel.status = (
                    TunnelStatus.ONLINE
                )
                tunnel.latency_ms = (
                    mtunnel_row.latency_ms
                )
                tunnel.last_switch_at = (
                    datetime.utcnow()
                )
                tunnel.mode = "auto"

                _fail_counts[
                    mtunnel_key
                ] = 0

                db.commit()

                print(
                    (
                        "[TransportManager] "
                        "FAILBACK "
                        f"tunnel={int(tunnel.id)} "
                        f"{old_active}->mtunnel "
                        f"stable={FAILBACK_SECONDS}s"
                    ),
                    flush=True,
                )

                return

        rows = {
            name: _member(
                db,
                tunnel.id,
                name,
            )
            for name in ORDER
        }

        # Enforce intended priority in DB/UI.
        for name, row in rows.items():
            if row:
                row.priority = PRIORITY[name]

        installed = [
            name
            for name in ORDER
            if _installed(rows[name])
        ]

        if not installed:
            tunnel.status = TunnelStatus.OFFLINE
            tunnel.latency_ms = None
            db.commit()
            return

        health = {}

        # --------------------------------------------
        # Backhaul
        # --------------------------------------------
        if "backhaul" in installed:
            health["backhaul"] = (
                await _backhaul_health(
                    tunnel,
                    iran,
                    exit_node,
                    db,
                )
            )
        else:
            health["backhaul"] = {
                "ok": False,
                "latency_ms": None,
                "error": "not_installed",
            }

        # --------------------------------------------
        # SSH TUN
        # --------------------------------------------
        if "ssh_tun" in installed:
            health["ssh_tun"] = (
                await _ssh_tun_health(
                    tunnel,
                    iran,
                    exit_node,
                    db,
                )
            )
        else:
            health["ssh_tun"] = {
                "ok": False,
                "latency_ms": None,
                "error": "not_installed",
            }

        # --------------------------------------------
        # SSH Relay
        # --------------------------------------------
        if "ssh_relay" in installed:
            health["ssh_relay"] = (
                await _ssh_relay_health(
                    tunnel,
                    iran,
                    db,
                )
            )
        else:
            health["ssh_relay"] = {
                "ok": False,
                "latency_ms": None,
                "error": "not_installed",
            }

        for name in ORDER:
            if rows[name]:
                _update_member(
                    rows[name],
                    health[name],
                )

        now_loop = (
            asyncio
            .get_running_loop()
            .time()
        )

        tid = int(tunnel.id)

        for name in ORDER:
            key = (
                tid,
                name,
            )

            if health[name]["ok"]:
                if (
                    _healthy_since.get(key)
                    is None
                ):
                    _healthy_since[key] = (
                        now_loop
                    )
            else:
                _healthy_since[key] = None

        preferred = next(
            (
                name
                for name in ORDER
                if name in installed
            ),
            None,
        )

        # Preferred means physical priority, not current fallback.
        # TWINPANEL_PREFERRED_MTUNNEL_V4
        tunnel.preferred_transport = (
            "mtunnel"
            if _installed(
                _member(
                    db,
                    tunnel.id,
                    "mtunnel",
                )
            )
            else preferred
        )

        active = str(
            tunnel.active_transport
            or ""
        ).strip().lower()

        if active not in ORDER:
            active = ""

        healthy_names = [
            name
            for name in ORDER
            if (
                name in installed
                and health[name]["ok"]
            )
        ]

        best_healthy = (
            healthy_names[0]
            if healthy_names
            else None
        )

        desired = active

        # Initial deployment:
        # after a fresh successful Backhaul probe,
        # promote it immediately.
        if (
            promote_now
            and health["backhaul"]["ok"]
        ):
            desired = "backhaul"

        elif not active:
            desired = (
                best_healthy
                or preferred
            )

        else:
            active_ok = (
                active in health
                and health[active]["ok"]
            )

            failure_key = (
                tid,
                active,
            )

            if not active_ok:
                _fail_counts[
                    failure_key
                ] = (
                    _fail_counts.get(
                        failure_key,
                        0,
                    )
                    + 1
                )

                if (
                    _fail_counts[
                        failure_key
                    ]
                    >= FAIL_THRESHOLD
                ):
                    desired = (
                        best_healthy
                        or active
                    )

            else:
                _fail_counts[
                    failure_key
                ] = 0

                active_index = (
                    ORDER.index(active)
                )

                # Fail back only after a better transport
                # has stayed healthy continuously.
                for candidate in (
                    ORDER[:active_index]
                ):
                    if candidate not in installed:
                        continue

                    if not health[candidate]["ok"]:
                        continue

                    healthy_since = (
                        _healthy_since.get(
                            (
                                tid,
                                candidate,
                            )
                        )
                    )

                    if (
                        healthy_since
                        is not None
                        and (
                            now_loop
                            - healthy_since
                        )
                        >= FAILBACK_SECONDS
                    ):
                        desired = candidate
                        break

        switched = (
            desired
            and desired != active
        )

        if desired:
            tunnel.active_transport = (
                desired
            )

        active_health = (
            health.get(
                desired or "",
                {
                    "ok": False,
                    "latency_ms": None,
                },
            )
        )

        # TWINPANEL_ANY_HEALTHY_IS_ONLINE_V4
        if (
            active_health["ok"]
            or best_healthy
        ):
            tunnel.status = (
                TunnelStatus.ONLINE
            )

        else:
            tunnel.status = (
                TunnelStatus.OFFLINE
            )

        tunnel.latency_ms = (
            active_health.get(
                "latency_ms"
            )
            if active_health["ok"]
            else (
                health[
                    best_healthy
                ].get("latency_ms")
                if best_healthy
                else None
            )
        )

        tunnel.mode = "auto"

        if switched:
            tunnel.last_switch_at = (
                datetime.utcnow()
            )

        db.commit()

        print(
            (
                f"[TransportManager] "
                f"tunnel={tid} "
                f"preferred={preferred} "
                f"active={tunnel.active_transport} "
                f"backhaul={health['backhaul']['ok']} "
                f"ssh_tun={health['ssh_tun']['ok']} "
                f"ssh_relay={health['ssh_relay']['ok']} "
                f"latency={tunnel.latency_ms}"
            ),
            flush=True,
        )

        if switched:
            print(
                (
                    f"[TransportManager] SWITCH "
                    f"tunnel={tid} "
                    f"{active or 'none'} "
                    f"-> {desired}"
                ),
                flush=True,
            )

    except Exception as exc:
        db.rollback()

        print(
            (
                f"[TransportManager] ERROR "
                f"tunnel={tunnel_id}: "
                f"{exc!r}"
            ),
            flush=True,
        )

    finally:
        db.close()


async def cycle(
    promote_now: bool = False,
):
    db = SessionLocal()

    try:
        ids = [
            int(item.id)
            for item in (
                db.query(Tunnel)
                .filter(
                    Tunnel.is_active.is_(True)
                )
                .order_by(
                    Tunnel.id.asc()
                )
                .all()
            )
        ]

    finally:
        db.close()

    for tunnel_id in ids:
        await _manage_one(
            tunnel_id,
            promote_now=promote_now,
        )


async def main():
    promote_now = (
        "--promote-now"
        in sys.argv
    )

    once = (
        "--once"
        in sys.argv
    )

    print(
        "TWINPANEL_TRANSPORT_MANAGER_V4_START",
        flush=True,
    )

    if once:
        await cycle(
            promote_now=promote_now,
        )
        return

    while True:
        try:
            await cycle()

        except Exception as exc:
            print(
                (
                    "[TransportManager] "
                    f"cycle error {exc!r}"
                ),
                flush=True,
            )

        await asyncio.sleep(
            LOOP_SECONDS
        )


if __name__ == "__main__":
    asyncio.run(main())
