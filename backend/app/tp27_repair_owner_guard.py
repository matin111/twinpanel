from __future__ import annotations

from . import tunnel_transport_manager_v8 as v8
from . import tunnel_transport_manager_v9 as v9
from .database import SessionLocal
from .models import TunnelTransport


# ============================================================
# TWINPANEL TP27 REPAIR OWNER GUARD
#
# TP27 Fast has its own carrier-only self-repair loop. The historical V8/V9
# managed self-heal pipeline owns TP2027/legacy repair and may provision SSH
# Relay. It must not mutate those transports for a tunnel whose TP27 carrier is
# owned by the dedicated TP27 repair loop.
#
# This guard changes repair ownership only. It does not change SmartAuto,
# health probing, active/preferred transport selection, VXLAN, or any carrier.
# ============================================================

MARKER = "TWINPANEL_TP27_REPAIR_OWNER_GUARD"
_applied = False


def _owned_in_session(db, tunnel_id: int) -> bool:
    row = (
        db.query(TunnelTransport.id)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == "tp27_fast",
            TunnelTransport.enabled.is_(True),
        )
        .first()
    )
    return row is not None


def tp27_repair_owns_tunnel(tunnel_id: int) -> bool:
    db = SessionLocal()
    try:
        return _owned_in_session(db, int(tunnel_id))
    finally:
        db.close()


def apply_tp27_repair_owner_guard() -> None:
    """Fence legacy managed repair while TP27 owns carrier recovery.

    Two checks are intentional:
    1. filter V8's scheduler candidates so no legacy repair is normally queued;
    2. re-check inside V9's worker so a task queued before TP27 installation
       cannot mutate legacy transports after TP27 becomes the repair owner.
    """

    global _applied
    if _applied:
        return

    original_managed_tunnel_ids = v8._managed_tunnel_ids
    original_run_self_heal = v9._run_self_heal_authoritative

    def managed_tunnel_ids_without_tp27(
        only_tunnel: int | None = None,
    ) -> list[int]:
        ids = original_managed_tunnel_ids(only_tunnel)
        if not ids:
            return []

        db = SessionLocal()
        try:
            owned = {
                int(row[0])
                for row in (
                    db.query(TunnelTransport.tunnel_id)
                    .filter(
                        TunnelTransport.tunnel_id.in_(ids),
                        TunnelTransport.transport == "tp27_fast",
                        TunnelTransport.enabled.is_(True),
                    )
                    .distinct()
                    .all()
                )
            }
        finally:
            db.close()

        return [int(tunnel_id) for tunnel_id in ids if int(tunnel_id) not in owned]

    async def run_self_heal_without_tp27(tunnel_id: int) -> None:
        if tp27_repair_owns_tunnel(int(tunnel_id)):
            print(
                f"{MARKER}_SKIP tunnel={int(tunnel_id)} "
                "owner=tp27_self_repair_v265",
                flush=True,
            )
            return

        await original_run_self_heal(int(tunnel_id))

    v8._managed_tunnel_ids = managed_tunnel_ids_without_tp27
    v9._run_self_heal_authoritative = run_self_heal_without_tp27

    _applied = True
    print(
        f"{MARKER}_ACTIVE scheduler_fence=1 worker_recheck=1",
        flush=True,
    )
