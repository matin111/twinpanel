from __future__ import annotations

from . import tunnel_transport_manager_v7 as v7
from .database import SessionLocal
from .models import Tunnel, TunnelTransport
from .smart_transport_auto_v21 import manage_2027_v21


# ============================================================
# TWINPANEL SMART AUTO DISCOVERY V38
#
# Root cause fixed here:
# V7.cycle historically called manage_2027() only when at least one overlay
# row already existed. Smart Auto V21 schedules its first modern candidate
# from inside manage_2027_v21(), so an AUTO tunnel with only legacy rows could
# never bootstrap GRE/GOST/AWG/Netrix and remained on SSH Relay forever.
#
# This wrapper preserves V7/V6 behavior for every normal/manual tunnel and
# intercepts only active AUTO tunnels that currently have zero rows in the
# effective overlay set. Those tunnels are handed directly to Smart Auto V21,
# allowing _maybe_schedule_install() to create the first candidate while the
# currently healthy legacy path remains active until a candidate is qualified.
# ============================================================

_BASE_CYCLE = None


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _partition_tunnels(
    only_tunnel: int | None = None,
) -> tuple[list[int], list[int]]:
    db = SessionLocal()
    try:
        query = (
            db.query(Tunnel)
            .filter(Tunnel.is_active.is_(True))
            .order_by(Tunnel.id.asc())
        )

        if only_tunnel is not None:
            query = query.filter(Tunnel.id == int(only_tunnel))

        discovery: list[int] = []
        regular: list[int] = []

        overlay_names = list(v7.OVERLAY_NAMES)

        for tunnel in query.all():
            tid = int(tunnel.id)

            if _name(tunnel.mode) != "auto":
                regular.append(tid)
                continue

            has_overlay_row = (
                db.query(TunnelTransport.id)
                .filter(
                    TunnelTransport.tunnel_id == tid,
                    TunnelTransport.transport.in_(overlay_names),
                )
                .first()
                is not None
            )

            if has_overlay_row:
                regular.append(tid)
            else:
                discovery.append(tid)

        return discovery, regular
    finally:
        db.close()


async def cycle_v38(
    dry_run: bool = False,
    only_tunnel: int | None = None,
) -> tuple[bool, str | None]:
    if _BASE_CYCLE is None:
        raise RuntimeError("smart_auto_discovery_v38_not_installed")

    discovery_ids, regular_ids = _partition_tunnels(only_tunnel)

    found = False
    best: str | None = None

    for tunnel_id in discovery_ids:
        print(
            "[SmartAutoDiscoveryV38] ZERO_CANDIDATE_AUTO "
            f"tunnel={int(tunnel_id)} action=smart_auto_bootstrap",
            flush=True,
        )

        managed, selected = await manage_2027_v21(
            int(tunnel_id),
            dry_run=dry_run,
        )

        found = found or bool(managed)
        if best is None and selected:
            best = selected

    # Run the proven V7/V6 path one tunnel at a time for everything else.
    # This is intentionally not called for discovery_ids, otherwise V7 would
    # immediately delegate those zero-overlay AUTO tunnels back to V6/SSH Relay
    # in the same cycle and recreate the original starvation bug.
    for tunnel_id in regular_ids:
        managed, selected = await _BASE_CYCLE(
            dry_run=dry_run,
            only_tunnel=int(tunnel_id),
        )

        found = found or bool(managed)
        if best is None and selected:
            best = selected

    return found, best


def install_smart_auto_discovery_v38() -> None:
    global _BASE_CYCLE

    if _BASE_CYCLE is None:
        _BASE_CYCLE = v7.cycle

    v7.cycle = cycle_v38

    print(
        "TWINPANEL_SMART_AUTO_DISCOVERY_V38_ACTIVE "
        "zero_candidate_auto=enabled "
        "legacy_fallback=preserved",
        flush=True,
    )
