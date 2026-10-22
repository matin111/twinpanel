from __future__ import annotations

from sqlalchemy import event, inspect, select

from .database import SessionLocal
from .models import Tunnel


# ============================================================
# TWINPANEL MANUAL AUTHORITY MANAGER GUARD V195
#
# The standalone Transport Manager is a separate process from the API. It owns
# several background writers (legacy V6/V7 selection, SmartAuto, self-heal,
# candidate installers and repair flows). A manager cycle may load a Tunnel in
# auto mode, spend a long time inside remote probes/installers, and then try to
# commit selection state after an administrator has already switched that same
# Tunnel to manual mode.
#
# Manual mode is an admin-owned authority boundary. This guard is installed only
# inside the standalone manager process. Immediately before every manager flush
# that attempts to change aggregate selection authority, it locks and re-reads
# the current Tunnel row from PostgreSQL. If the committed row is now manual,
# the stale manager values are replaced with the current DB authority values.
# Other dirty fields (status/latency/health telemetry) are intentionally left
# untouched and may still be persisted.
#
# The SELECT ... FOR UPDATE makes the decision atomic with the subsequent flush:
# - admin commit first -> manager sees manual and drops its stale authority write
# - manager lock first -> admin waits, then its manual selection commits last
#
# This module is NOT installed by the FastAPI/API process, so legitimate admin
# transitions (manual <-> auto) remain owned by the existing admin endpoints.
# ============================================================


PROTECTED_AUTHORITY_FIELDS = (
    "mode",
    "active_transport",
    "preferred_transport",
    "last_switch_at",
)

_installed = False


def _mode(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "manual").strip().lower()


def _authority_change_fields(tunnel: Tunnel) -> list[str]:
    state = inspect(tunnel)
    changed: list[str] = []

    for name in PROTECTED_AUTHORITY_FIELDS:
        if state.attrs[name].history.has_changes():
            changed.append(name)

    return changed


def _protect_manual_authority(session, flush_context, instances) -> None:
    """Drop stale manager authority writes after Manual wins in PostgreSQL."""

    for tunnel in list(session.dirty):
        if not isinstance(tunnel, Tunnel):
            continue

        tunnel_id = getattr(tunnel, "id", None)
        if tunnel_id is None:
            continue

        changed = _authority_change_fields(tunnel)
        if not changed:
            continue

        # SessionLocal has autoflush=False, but keep this explicit so a future
        # sessionmaker change cannot flush the stale values before the lock/read.
        with session.no_autoflush:
            current = session.execute(
                select(
                    Tunnel.mode,
                    Tunnel.active_transport,
                    Tunnel.preferred_transport,
                    Tunnel.last_switch_at,
                )
                .where(Tunnel.id == int(tunnel_id))
                .with_for_update()
            ).one_or_none()

        if current is None or _mode(current.mode) != "manual":
            continue

        # Restore only authority fields from the current committed row. Any
        # status/latency/health telemetry already dirty on this ORM object stays
        # dirty and is allowed to flush in Manual mode.
        tunnel.mode = current.mode
        tunnel.active_transport = current.active_transport
        tunnel.preferred_transport = current.preferred_transport
        tunnel.last_switch_at = current.last_switch_at

        print(
            "[ManualAuthorityV195] BLOCK_STALE_MANAGER_WRITE "
            f"tunnel={int(tunnel_id)} fields={','.join(changed)} "
            f"active={current.active_transport} "
            f"preferred={current.preferred_transport}",
            flush=True,
        )


def install_manual_authority_manager_guard_v195() -> None:
    """Install the manager-process-only flush guard exactly once."""

    global _installed

    if _installed:
        return

    event.listen(
        SessionLocal.class_,
        "before_flush",
        _protect_manual_authority,
    )
    _installed = True

    print(
        "TWINPANEL_MANUAL_AUTHORITY_MANAGER_GUARD_V195_ACTIVE "
        "protected=mode,active_transport,preferred_transport,last_switch_at",
        flush=True,
    )


def remove_manual_authority_manager_guard_v195() -> None:
    """Test-only uninstall helper; production manager never calls this."""

    global _installed

    if not _installed:
        return

    event.remove(
        SessionLocal.class_,
        "before_flush",
        _protect_manual_authority,
    )
    _installed = False
