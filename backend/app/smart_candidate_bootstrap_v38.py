from __future__ import annotations

import asyncio

from .database import SessionLocal
from .models import Tunnel
from . import smart_transport_auto_v21 as smart


# ============================================================
# TWINPANEL SMART CANDIDATE BOOTSTRAP V38
#
# Smart Auto V21 can install/qualify/benchmark modern candidate transports,
# but the legacy V7 cycle only enters the Smart Auto selector after at least
# one overlay/candidate row already exists. Existing production tunnels that
# only have legacy rows (for example ssh_relay) therefore never reach V21's
# internal _maybe_schedule_install() path and can remain permanently on a
# slow fallback.
#
# This supervisor closes only that zero-row lifecycle gap. It does not install
# transports itself and does not modify tunnel state. It invokes the existing
# Smart Auto scheduler for every active AUTO tunnel. V21 still owns:
#   * global single-install limiting;
#   * per-tunnel install cooldown;
#   * candidate order;
#   * Netrix availability/licensing guard;
#   * installer error handling;
#   * health, stability, benchmark and promotion policy.
#
# Once the first candidate row exists, the normal V7/V21 manager path becomes
# authoritative. Calling the scheduler after that remains safe/idempotent and
# lets V21 progressively install the remaining candidates.
# ============================================================

LOOP_SECONDS = 5.0


def _active_auto_tunnel_ids() -> list[int]:
    db = SessionLocal()
    try:
        return [
            int(row[0])
            for row in (
                db.query(Tunnel.id)
                .filter(
                    Tunnel.is_active.is_(True),
                    Tunnel.mode == "auto",
                )
                .order_by(Tunnel.id.asc())
                .all()
            )
        ]
    finally:
        db.close()


async def cycle() -> None:
    for tunnel_id in _active_auto_tunnel_ids():
        try:
            smart._maybe_schedule_install(int(tunnel_id))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "[SmartCandidateBootstrapV38] "
                f"SCHEDULE_ERROR tunnel={int(tunnel_id)} "
                f"error={repr(exc)[:1000]}",
                flush=True,
            )


async def reconciler_loop() -> None:
    print(
        "TWINPANEL_SMART_CANDIDATE_BOOTSTRAP_V38_ACTIVE "
        "mode=auto scheduler=smart_auto_v21 interval=5s",
        flush=True,
    )

    while True:
        try:
            await cycle()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "[SmartCandidateBootstrapV38] "
                f"cycle error {repr(exc)[:1000]}",
                flush=True,
            )

        await asyncio.sleep(LOOP_SECONDS)
