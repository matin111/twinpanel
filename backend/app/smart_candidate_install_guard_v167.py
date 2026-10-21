from __future__ import annotations

from . import smart_transport_auto_v21 as smart
from . import tunnel_transport_manager_v7 as v7
from .database import SessionLocal
from .models import TunnelTransport


# ============================================================
# TWINPANEL SMART CANDIDATE INSTALL GUARD V167
#
# A candidate installer marks its row as `installing` before it starts the
# Exit/Iran services. SmartAuto health runs concurrently every manager pass.
# Without an install guard, health can observe the intentional half-installed
# window (for example Exit active while Iran is not ready yet), mark the row
# offline, and quarantine it for 120 seconds.
#
# V167 makes `installing` an explicit transient lifecycle state:
#   * remote candidate health is not executed while the row is installing;
#   * the shared V7 overlay DB writer does not overwrite installing rows;
#   * the installer remains the sole writer until it finishes online/failed;
#   * the next normal manager pass probes the completed candidate normally.
# ============================================================

MARKER = "TWINPANEL_SMART_CANDIDATE_INSTALL_GUARD_V167"

_applied = False
_original_candidate_health = smart.candidate_health_remote_v21
_original_write_overlay_rows = v7.write_overlay_rows


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _candidate_is_installing(tunnel_id: int, name: str) -> bool:
    db = SessionLocal()
    try:
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == int(tunnel_id),
                TunnelTransport.transport == _name(name),
            )
            .first()
        )
        return bool(
            row is not None
            and row.enabled
            and _status(row.status) == "installing"
        )
    finally:
        db.close()


async def candidate_health_remote_install_guard_v167(
    tunnel_id: int,
    name: str,
    cfg: dict,
) -> tuple[str, dict]:
    normalized = _name(name)

    if (
        normalized in smart.CANDIDATE_NAMES
        and _candidate_is_installing(int(tunnel_id), normalized)
    ):
        return normalized, {
            "ok": False,
            "latency_ms": None,
            "packet_loss_pct": None,
            "restart_count": None,
            "stable_seconds": 0.0,
            "installing": True,
            "skip_persist": True,
            "error": "candidate_install_in_progress",
        }

    return await _original_candidate_health(
        int(tunnel_id),
        normalized,
        cfg,
    )


def write_overlay_rows_install_guard_v167(
    rows: list[TunnelTransport],
    health: dict[str, dict],
) -> None:
    # The installer is authoritative for rows in the installing state. Do not
    # let the generic overlay persistence path turn that transient state into
    # offline merely because one side has not finished starting yet.
    ready_rows = [
        row
        for row in rows
        if _status(row.status) != "installing"
    ]
    _original_write_overlay_rows(ready_rows, health)


def apply_smart_candidate_install_guard_v167() -> None:
    global _applied

    if _applied:
        return

    # install_smart_transport_auto_v21() binds V7 to the SmartAuto health
    # function before this layer is applied. Patch both symbols so direct calls
    # and V7 probe_overlays() share the same lifecycle guard.
    smart.candidate_health_remote_v21 = candidate_health_remote_install_guard_v167
    v7.overlay_health_remote = candidate_health_remote_install_guard_v167
    v7.write_overlay_rows = write_overlay_rows_install_guard_v167

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "installing_probe=deferred "
        "installing_persist=skipped "
        "installer=authoritative",
        flush=True,
    )
