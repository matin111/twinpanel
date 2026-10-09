from __future__ import annotations

import argparse
import asyncio
import json
import re
import shlex
from datetime import UTC, datetime

from .database import SessionLocal
from .models import (
    Node,
    Tunnel,
    TunnelPeerState,
    TunnelStatus,
    TunnelTransport,
)
from .routers.provision import ssh_connect_saved
from .tunnel_transport_manager import (
    _member,
    _update_member,
)
from . import tunnel_transport_manager_v6 as v6


# ============================================================
# TWINPANEL TRANSPORT MANAGER V7
#
# 2027 Overlay order comes from tunnel_transports.priority.
#
# Current production priorities:
#
#   10  quic_2027
#   20  arq_2027
#   30  kcp_2027
#   40  tcp_2027
#   90  mtunnel
#  100  backhaul
#  200  ssh_tun
#  300  ssh_relay
#
# 2027 overlays currently depend on Backhaul/BH5 as carrier.
#
# Tunnels without 2027 rows are delegated to V6 unchanged.
# ============================================================


LOOP_SECONDS = 5

ACTIVE_FAILURE_THRESHOLD = 2
FAILBACK_SECONDS = 45


OVERLAY_NAMES = {
    "quic_2027",
    "arq_2027",
    "kcp_2027",
    "tcp_2027",
}


LEGACY_NAMES = {
    "mtunnel",
    "backhaul",
    "ssh_tun",
    "ssh_relay",
}


SUPPORTED_NAMES = (
    OVERLAY_NAMES
    | LEGACY_NAMES
)


_failure_count: dict[int, int] = {}

_promotion_since: dict[int, float | None] = {}

_promotion_target: dict[int, str | None] = {}


def utcnow():
    return datetime.now(
        UTC
    ).replace(
        tzinfo=None
    )


def latency_of(
    health: dict | None,
) -> int | None:

    if not health:
        return None

    value = health.get(
        "latency_ms"
    )

    try:
        if value is None:
            return None

        return int(
            value
        )

    except Exception:
        return None


def loss_of(
    text: str,
) -> float | None:

    m = re.search(
        r"([0-9]+(?:\.[0-9]+)?)%\s+packet loss",
        text,
    )

    if not m:
        return None

    try:
        return float(
            m.group(1)
        )

    except Exception:
        return None


def latency_from_ping(
    text: str,
) -> int | None:

    for line in text.splitlines():

        if "min/avg/max" not in line:
            continue

        if "=" not in line:
            continue

        try:
            right = (
                line
                .split("=", 1)[1]
                .strip()
            )

            avg = (
                right
                .split("/")[1]
            )

            return int(
                float(avg)
            )

        except Exception:
            pass

    return None


def config_of(
    row: TunnelTransport,
) -> dict:

    if not row.config_text:
        return {}

    try:
        value = json.loads(
            row.config_text
        )

        if isinstance(
            value,
            dict,
        ):
            return value

    except Exception:
        pass

    return {}


def enabled_rows(
    db,
    tunnel_id: int,
) -> list[TunnelTransport]:

    rows = (
        db.query(
            TunnelTransport
        )
        .filter(
            TunnelTransport.tunnel_id
            == int(tunnel_id),
            TunnelTransport.enabled
            .is_(True),
        )
        .order_by(
            TunnelTransport.priority.asc(),
            TunnelTransport.id.asc(),
        )
        .all()
    )

    return [
        row
        for row in rows
        if str(
            row.transport or ""
        ).strip().lower()
        in SUPPORTED_NAMES
    ]


def enabled_overlay_rows(
    db,
    tunnel_id: int,
) -> list[TunnelTransport]:

    return [
        row
        for row in enabled_rows(
            db,
            tunnel_id,
        )
        if str(
            row.transport
        ).strip().lower()
        in OVERLAY_NAMES
    ]


async def overlay_health_remote(
    tunnel_id: int,
    name: str,
    cfg: dict,
) -> tuple[str, dict]:

    db = SessionLocal()

    conn = None

    try:

        tunnel = db.get(
            Tunnel,
            int(tunnel_id),
        )

        if not tunnel:
            return (
                name,
                {
                    "ok": False,
                    "latency_ms": None,
                    "error": "tunnel_missing",
                },
            )

        iran = db.get(
            Node,
            int(
                tunnel.iran_node_id
            ),
        )

        exit_node = db.get(
            Node,
            int(
                tunnel.exit_node_id
            ),
        )

        if not iran or not exit_node:

            return (
                name,
                {
                    "ok": False,
                    "latency_ms": None,
                    "error": "node_missing",
                },
            )


        iface = str(
            cfg.get(
                "interface"
            )
            or ""
        ).strip()

        source_ip = str(
            cfg.get(
                "iran_ip"
            )
            or ""
        ).strip()

        peer_ip = str(
            cfg.get(
                "exit_ip"
            )
            or ""
        ).strip()

        service = str(
            cfg.get(
                "iran_service"
            )
            or ""
        ).strip()

        expected_exit_ip = str(
            exit_node.public_ip
            or ""
        ).strip()


        missing = []

        if not iface:
            missing.append(
                "interface"
            )

        if not source_ip:
            missing.append(
                "iran_ip"
            )

        if not peer_ip:
            missing.append(
                "exit_ip"
            )

        if not service:
            missing.append(
                "iran_service"
            )

        if not expected_exit_ip:
            missing.append(
                "exit_public_ip"
            )


        if missing:

            return (
                name,
                {
                    "ok": False,
                    "latency_ms": None,
                    "error": (
                        "overlay_config_missing:"
                        + ",".join(missing)
                    ),
                },
            )


        conn = await ssh_connect_saved(
            iran,
            db,
        )


        cmd = f"""
set +e

systemctl is-active --quiet \
 {shlex.quote(service)}

SERVICE_RC=$?

ip link show \
 {shlex.quote(iface)} \
 >/dev/null 2>&1

IFACE_RC=$?

ip addr show \
 {shlex.quote(iface)} \
 2>/dev/null \
 | grep -qw \
 {shlex.quote(source_ip)}

ADDR_RC=$?

echo "TP_SERVICE_RC=$SERVICE_RC"
echo "TP_IFACE_RC=$IFACE_RC"
echo "TP_ADDR_RC=$ADDR_RC"

if [ "$SERVICE_RC" -ne 0 ] \
 || [ "$IFACE_RC" -ne 0 ] \
 || [ "$ADDR_RC" -ne 0 ]
then
    exit 31
fi

test -x \
 /usr/local/sbin/tp2027-egress-probe

/usr/local/sbin/tp2027-egress-probe \
 {shlex.quote(iface)} \
 {shlex.quote(source_ip)} \
 {shlex.quote(peer_ip)} \
 {shlex.quote(expected_exit_ip)}
"""

        result = await conn.run(
            cmd,
            check=False,
            timeout=70,
        )

        stdout = (
            result.stdout
            or ""
        )

        stderr = (
            result.stderr
            or ""
        )

        ok = (
            result.exit_status
            == 0
            and "FULL_EGRESS=PASS"
            in stdout
        )

        latency = latency_from_ping(
            stdout
        )

        loss = loss_of(
            stdout
        )

        if ok:

            return (
                name,
                {
                    "ok": True,
                    "latency_ms": latency,
                    "packet_loss_pct": loss,
                    "error": None,
                },
            )


        detail = (
            stdout[-1000:]
            + " | "
            + stderr[-500:]
        )

        return (
            name,
            {
                "ok": False,
                "latency_ms": None,
                "packet_loss_pct": loss,
                "error": (
                    f"{name}_full_egress_failed: "
                    + detail
                )[:1500],
            },
        )


    except Exception as exc:

        return (
            name,
            {
                "ok": False,
                "latency_ms": None,
                "error": (
                    f"{name}_probe_exception:"
                    + repr(exc)
                )[:1500],
            },
        )


    finally:

        if conn:

            try:
                conn.close()
                await conn.wait_closed()

            except Exception:
                pass

        db.close()


async def probe_overlays(
    tunnel_id: int,
    rows: list[TunnelTransport],
) -> dict[str, dict]:

    jobs = []

    for row in rows:

        name = str(
            row.transport
        ).strip().lower()

        cfg = config_of(
            row
        )

        jobs.append(
            overlay_health_remote(
                int(tunnel_id),
                name,
                cfg,
            )
        )


    if not jobs:
        return {}


    results = await asyncio.gather(
        *jobs,
        return_exceptions=True,
    )


    health: dict[str, dict] = {}


    for item in results:

        if isinstance(
            item,
            Exception,
        ):
            continue

        name, result = item

        health[
            name
        ] = result


    for row in rows:

        name = str(
            row.transport
        ).strip().lower()

        if name not in health:

            health[name] = {
                "ok": False,
                "latency_ms": None,
                "error": (
                    "overlay_probe_missing_result"
                ),
            }


    return health


async def probe_legacy(
    tunnel,
    iran,
    exit_node,
    db,
    rows: list[TunnelTransport],
) -> tuple[
    dict[str, dict],
    str | None,
]:

    health: dict[str, dict] = {}

    best = None


    legacy_rows = [
        row
        for row in rows
        if str(
            row.transport
        ).strip().lower()
        in LEGACY_NAMES
    ]


    for row in legacy_rows:

        name = str(
            row.transport
        ).strip().lower()


        try:

            result = (
                await v6._full_health_for(
                    name,
                    tunnel,
                    iran,
                    exit_node,
                    db,
                )
            )

        except Exception as exc:

            result = {
                "ok": False,
                "latency_ms": None,
                "error": (
                    f"legacy_health_exception:"
                    + repr(exc)
                )[:1200],
            }


        health[
            name
        ] = result


        _update_member(
            row,
            result,
        )


        if result.get(
            "ok"
        ):

            best = name
            break


    return health, best


def write_overlay_rows(
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> None:

    for row in rows:

        name = str(
            row.transport
        ).strip().lower()

        result = health.get(
            name
        )

        if result is None:
            continue

        _update_member(
            row,
            result,
        )


def priority_map(
    rows: list[TunnelTransport],
) -> dict[str, int]:

    return {
        str(
            row.transport
        ).strip().lower():
            int(row.priority)

        for row in rows
    }


def best_overlay(
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> str | None:

    for row in rows:

        name = str(
            row.transport
        ).strip().lower()

        result = health.get(
            name
        )

        if (
            result
            and result.get(
                "ok"
            )
        ):
            return name

    return None


def update_peers(
    db,
    tunnel_id: int,
    selected: str,
    health: dict,
) -> None:

    now = utcnow()

    latency = latency_of(
        health
    )

    rows = (
        db.query(
            TunnelPeerState
        )
        .filter(
            TunnelPeerState.tunnel_id
            == int(tunnel_id)
        )
        .all()
    )

    for peer in rows:

        peer.selected_transport = (
            selected
        )

        peer.endpoint_reachable = True
        peer.tunnel_reachable = True

        peer.latency_ms = latency

        peer.last_error = None

        peer.updated_at = now


def switch_to(
    db,
    tunnel,
    name: str,
    health: dict,
    preferred: str,
    reason: str,
) -> None:

    old = str(
        tunnel.active_transport
        or ""
    ).strip().lower()

    tunnel.mode = "auto"

    tunnel.active_transport = name

    tunnel.preferred_transport = preferred

    tunnel.status = (
        TunnelStatus.ONLINE
    )

    tunnel.latency_ms = latency_of(
        health
    )

    tunnel.last_switch_at = utcnow()


    update_peers(
        db,
        int(tunnel.id),
        name,
        health,
    )


    db.commit()


    _failure_count[
        int(tunnel.id)
    ] = 0

    _promotion_since[
        int(tunnel.id)
    ] = None

    _promotion_target[
        int(tunnel.id)
    ] = None


    print(
        f"[TransportManagerV7] SWITCH "
        f"tunnel={int(tunnel.id)} "
        f"{old or 'none'}->{name} "
        f"reason={reason} "
        f"latency={latency_of(health)}",
        flush=True,
    )


def keep_online(
    db,
    tunnel,
    active: str,
    health: dict | None,
    preferred: str,
) -> None:

    tunnel.mode = "auto"

    tunnel.preferred_transport = (
        preferred
    )

    tunnel.status = (
        TunnelStatus.ONLINE
    )


    if health and health.get(
        "ok"
    ):

        tunnel.latency_ms = latency_of(
            health
        )


    db.commit()


def set_offline(
    db,
    tunnel,
    preferred: str,
) -> None:

    tunnel.mode = "auto"

    tunnel.preferred_transport = (
        preferred
    )

    tunnel.status = (
        TunnelStatus.OFFLINE
    )

    tunnel.latency_ms = None

    db.commit()


async def manage_2027(
    tunnel_id: int,
    dry_run: bool = False,
) -> tuple[bool, str | None]:

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
            return False, None


        if str(
            tunnel.mode
            or "manual"
        ).strip().lower() != "auto":

            return False, None


        iran = db.get(
            Node,
            int(
                tunnel.iran_node_id
            ),
        )

        exit_node = db.get(
            Node,
            int(
                tunnel.exit_node_id
            ),
        )

        if not iran or not exit_node:
            return False, None


        rows = enabled_rows(
            db,
            int(tunnel.id),
        )


        overlay_rows = [
            row
            for row in rows
            if str(
                row.transport
            ).strip().lower()
            in OVERLAY_NAMES
        ]


        if not overlay_rows:
            return False, None


        preferred = str(
            overlay_rows[0].transport
        ).strip().lower()


        priorities = priority_map(
            rows
        )


        overlay_health = (
            await probe_overlays(
                int(tunnel.id),
                overlay_rows,
            )
        )


        overlay_best = best_overlay(
            overlay_rows,
            overlay_health,
        )


        if dry_run:

            print(
                f"[TransportManagerV7] "
                f"DRYRUN tunnel={int(tunnel.id)} "
                f"preferred={preferred} "
                f"best={overlay_best}",
                flush=True,
            )

            for row in overlay_rows:

                name = str(
                    row.transport
                ).strip().lower()

                h = overlay_health.get(
                    name,
                    {},
                )

                print(
                    f"[TransportManagerV7] "
                    f"DRYRUN transport={name} "
                    f"ok={int(bool(h.get('ok')))} "
                    f"latency={latency_of(h)} "
                    f"loss={h.get('packet_loss_pct')}",
                    flush=True,
                )


            print(
                "V7_DRYRUN_BEST="
                + (
                    overlay_best
                    or "none"
                ),
                flush=True,
            )

            return (
                overlay_best is not None,
                overlay_best,
            )


        write_overlay_rows(
            overlay_rows,
            overlay_health,
        )


        health = dict(
            overlay_health
        )


        best = overlay_best


        #
        # If no 2027 overlay is usable, probe old independent
        # transports in their DB priority order.
        #
        if best is None:

            legacy_health, legacy_best = (
                await probe_legacy(
                    tunnel,
                    iran,
                    exit_node,
                    db,
                    rows,
                )
            )

            health.update(
                legacy_health
            )

            best = legacy_best


        active = str(
            tunnel.active_transport
            or ""
        ).strip().lower()


        active_health = health.get(
            active
        )


        tid = int(
            tunnel.id
        )


        #
        # No healthy transport.
        #
        if best is None:

            _promotion_since[
                tid
            ] = None

            _promotion_target[
                tid
            ] = None


            _failure_count[
                tid
            ] = (
                _failure_count.get(
                    tid,
                    0,
                )
                + 1
            )


            if (
                _failure_count[
                    tid
                ]
                >= ACTIVE_FAILURE_THRESHOLD
            ):

                set_offline(
                    db,
                    tunnel,
                    preferred,
                )


            print(
                f"[TransportManagerV7] "
                f"tunnel={tid} "
                f"healthy=none "
                f"fail_count="
                f"{_failure_count[tid]}",
                flush=True,
            )

            return True, None


        #
        # Active already equals best.
        #
        if active == best:

            _failure_count[
                tid
            ] = 0

            _promotion_since[
                tid
            ] = None

            _promotion_target[
                tid
            ] = None


            keep_online(
                db,
                tunnel,
                active,
                health.get(
                    active
                ),
                preferred,
            )


            print(
                f"[TransportManagerV7] "
                f"tunnel={tid} "
                f"active={active} "
                f"status=online "
                f"latency="
                f"{latency_of(health.get(active))}",
                flush=True,
            )

            return True, active


        #
        # If active is a 2027 overlay and we actually probed it,
        # require two consecutive physical failures before failover.
        #
        if (
            active in OVERLAY_NAMES
            and active_health is not None
            and not active_health.get(
                "ok"
            )
        ):

            _promotion_since[
                tid
            ] = None

            _promotion_target[
                tid
            ] = None


            _failure_count[
                tid
            ] = (
                _failure_count.get(
                    tid,
                    0,
                )
                + 1
            )


            if (
                _failure_count[
                    tid
                ]
                >= ACTIVE_FAILURE_THRESHOLD
            ):

                switch_to(
                    db,
                    tunnel,
                    best,
                    health[
                        best
                    ],
                    preferred,
                    "active_failed_confirmed",
                )

                return True, best


            keep_online(
                db,
                tunnel,
                active,
                None,
                preferred,
            )


            print(
                f"[TransportManagerV7] "
                f"tunnel={tid} "
                f"active={active} "
                f"probe_failed=1 "
                f"count="
                f"{_failure_count[tid]} "
                f"candidate={best}",
                flush=True,
            )

            return True, active


        #
        # Legacy active with no overlays healthy:
        # legacy probe tells us whether active is bad.
        #
        if (
            active in LEGACY_NAMES
            and overlay_best is None
            and active_health is not None
            and not active_health.get(
                "ok"
            )
        ):

            _failure_count[
                tid
            ] = (
                _failure_count.get(
                    tid,
                    0,
                )
                + 1
            )


            if (
                _failure_count[
                    tid
                ]
                >= ACTIVE_FAILURE_THRESHOLD
            ):

                switch_to(
                    db,
                    tunnel,
                    best,
                    health[
                        best
                    ],
                    preferred,
                    "legacy_active_failed_confirmed",
                )

                return True, best


            keep_online(
                db,
                tunnel,
                active,
                None,
                preferred,
            )

            return True, active


        #
        # A higher-priority transport is healthy.
        # Require continuous health before failback/promotion.
        #
        active_priority = priorities.get(
            active,
            10**9,
        )

        best_priority = priorities.get(
            best,
            10**9,
        )


        if (
            best_priority
            < active_priority
        ):

            now = asyncio.get_running_loop().time()


            if (
                _promotion_target.get(
                    tid
                )
                != best
            ):

                _promotion_target[
                    tid
                ] = best

                _promotion_since[
                    tid
                ] = now


            since = _promotion_since.get(
                tid
            )


            stable = (
                0
                if since is None
                else now - since
            )


            if (
                stable
                >= FAILBACK_SECONDS
            ):

                switch_to(
                    db,
                    tunnel,
                    best,
                    health[
                        best
                    ],
                    preferred,
                    "higher_priority_stable",
                )

                return True, best


            keep_online(
                db,
                tunnel,
                active,
                active_health,
                preferred,
            )


            print(
                f"[TransportManagerV7] "
                f"tunnel={tid} "
                f"active={active} "
                f"better={best} "
                f"stable={int(stable)}/"
                f"{FAILBACK_SECONDS}",
                flush=True,
            )

            return True, active


        #
        # Active is unsupported/stale, or a lower-priority
        # healthy candidate is the only remaining path.
        #
        if active not in SUPPORTED_NAMES:

            switch_to(
                db,
                tunnel,
                best,
                health[
                    best
                ],
                preferred,
                "unsupported_active",
            )

            return True, best


        #
        # Current path has no direct health result but a usable
        # candidate exists. Keep existing active unless it is known bad.
        #
        keep_online(
            db,
            tunnel,
            active,
            active_health,
            preferred,
        )

        return True, active


    finally:

        db.close()


async def cycle(
    dry_run: bool = False,
    only_tunnel: int | None = None,
) -> tuple[
    bool,
    str | None,
]:

    db = SessionLocal()

    try:

        query = (
            db.query(
                Tunnel
            )
            .filter(
                Tunnel.is_active
                .is_(True)
            )
            .order_by(
                Tunnel.id.asc()
            )
        )


        if only_tunnel is not None:

            query = query.filter(
                Tunnel.id
                == int(
                    only_tunnel
                )
            )


        ids = [
            int(
                item.id
            )
            for item in query.all()
        ]


    finally:
        db.close()


    found_2027 = False
    best_2027 = None


    for tunnel_id in ids:

        db = SessionLocal()

        try:

            has_2027 = (
                db.query(
                    TunnelTransport
                )
                .filter(
                    TunnelTransport.tunnel_id
                    == tunnel_id,
                    TunnelTransport.transport
                    .in_(
                        list(
                            OVERLAY_NAMES
                        )
                    ),
                )
                .count()
                > 0
            )

        finally:
            db.close()


        if has_2027:

            managed, best = (
                await manage_2027(
                    tunnel_id,
                    dry_run=dry_run,
                )
            )

            found_2027 = (
                found_2027
                or managed
            )

            if best_2027 is None:
                best_2027 = best


        elif not dry_run:

            #
            # Preserve V6 behavior exactly for every tunnel
            # which has no 2027 overlay rows.
            #
            await v6._manage_one(
                tunnel_id
            )


    return (
        found_2027,
        best_2027,
    )


async def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--once",
        action="store_true",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--tunnel-id",
        type=int,
        default=None,
    )

    args = parser.parse_args()


    print(
        "TWINPANEL_TRANSPORT_MANAGER_V7_START",
        flush=True,
    )


    if args.once:

        found, best = await cycle(
            dry_run=args.dry_run,
            only_tunnel=args.tunnel_id,
        )


        if args.dry_run:

            if not found or not best:
                raise SystemExit(3)


        return


    while True:

        try:

            await cycle()

        except Exception as exc:

            print(
                "[TransportManagerV7] "
                f"cycle error {exc!r}",
                flush=True,
            )


        await asyncio.sleep(
            LOOP_SECONDS
        )


if __name__ == "__main__":
    asyncio.run(
        main()
    )
