from __future__ import annotations

from . import tunnel_transport_manager_v8 as v8
from . import tunnel_transport_manager_v9 as v9
from .database import SessionLocal
from .models import Tunnel, TunnelTransport


# ============================================================
# TWINPANEL TP27 REPAIR OWNER GUARD
#
# TP27 Fast has its own carrier-only self-repair loop. The historical V8/V9
# managed self-heal pipeline owns TP2027/legacy repair and may provision SSH
# Relay. It must not mutate those transports while the same logical tunnel is
# inside TP27's repair ownership domain.
#
# A healthy TP27 standby on an AUTO tunnel does not claim global ownership;
# unrelated legacy recovery may proceed until TP27 itself becomes relevant.
#
# This guard changes repair ownership only. It does not change SmartAuto,
# health probing, active/preferred transport selection, VXLAN, or any carrier.
# ============================================================

MARKER = "TWINPANEL_TP27_REPAIR_OWNER_GUARD"
_applied = False


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _owned_in_session(db, tunnel_id: int) -> bool:
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None or not bool(tunnel.is_active):
        return False

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == "tp27_fast",
            TunnelTransport.enabled.is_(True),
        )
        .first()
    )
    if row is None:
        return False

    mode = str(tunnel.mode or "manual").strip().lower()
    active = str(tunnel.active_transport or "").strip().lower()
    preferred = str(tunnel.preferred_transport or "").strip().lower()
    tp27_state = _status(row.status)

    return bool(
        mode == "manual"
        or active == "tp27_fast"
        or preferred == "tp27_fast"
        or tp27_state in {"offline", "failed", "degraded"}
    )


def tp27_repair_owns_tunnel(tunnel_id: int) -> bool:
    db = SessionLocal()
    try:
        return _owned_in_session(db, int(tunnel_id))
    finally:
        db.close()


def apply_tp27_repair_owner_guard() -> None:
    """Fence legacy managed repair while TP27 owns carrier recovery.

    Two checks are intentional:
    1. filter V8's scheduler candidates so no conflicting repair is queued;
    2. re-check inside V9's worker so a stale queued task cannot mutate legacy
       transports after TP27 enters its repair ownership domain.
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
            return [
                int(tunnel_id)
                for tunnel_id in ids
                if not _owned_in_session(db, int(tunnel_id))
            ]
        finally:
            db.close()

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
