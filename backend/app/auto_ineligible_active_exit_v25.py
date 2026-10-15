from __future__ import annotations

import asyncio

from . import transport_policy_v20 as v20
from . import tunnel_transport_manager_v7 as v7
from .auto_eligibility_v24 import auto_eligible
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport


# ============================================================
# TWINPANEL AUTO INELIGIBLE ACTIVE EXIT V25
#
# V24 excludes an explicitly auto_eligible=false member from Auto ranking,
# but V20's normal promotion hold/dwell can intentionally leave an already-
# active member in place for a while. That is desirable for ordinary quality
# changes, but not for an explicit administrative Auto exclusion.
#
# V25 gives the exclusion operational authority:
#   * Manual remains authoritative and unchanged.
#   * Only Auto tunnels are considered.
#   * If the CURRENT active row is explicitly auto_eligible=false, select the
#     best healthy eligible candidate using V20's existing ranking/probes.
#   * Re-probe that target immediately and switch only when fresh health is OK.
#   * If there is no healthy replacement, keep the current path and delegate to
#     V20 rather than causing an outage.
# ============================================================


_BASE_MANAGE = None


def _name(value: object) -> str:
    return str(value or "").strip().lower()


def _active_row(
    rows: list[TunnelTransport],
    active: str,
) -> TunnelTransport | None:
    wanted = _name(active)

    return next(
        (
            row
            for row in rows
            if _name(getattr(row, "transport", "")) == wanted
        ),
        None,
    )


def active_is_explicitly_ineligible(
    rows: list[TunnelTransport],
    active: str,
) -> bool:
    row = _active_row(rows, active)
    return bool(row is not None and not auto_eligible(row))


def should_immediate_exit(
    rows: list[TunnelTransport],
    active: str,
    best: str | None,
) -> bool:
    current = _name(active)
    candidate = _name(best)

    return bool(
        current
        and candidate
        and candidate != current
        and active_is_explicitly_ineligible(rows, current)
    )


async def _fresh_health(
    tunnel: Tunnel,
    iran: Node,
    exit_node: Node,
    db,
    target: TunnelTransport,
) -> dict:
    name = _name(target.transport)

    if name in v20.MODERN_NAMES:
        snapshot = await v7.probe_overlays(
            int(tunnel.id),
            [target],
        )
        return dict(snapshot.get(name) or {})

    if name in v20.LEGACY_NAMES:
        return dict(
            await v20._probe_legacy(
                name,
                tunnel,
                iran,
                exit_node,
                db,
            )
            or {}
        )

    return {
        "ok": False,
        "latency_ms": None,
        "error": "v25_target_not_supported",
    }


async def manage_2027_v25(
    tunnel_id: int,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    base = _BASE_MANAGE or v20.manage_2027_v20
    tid = int(tunnel_id)

    if dry_run:
        return await base(tid, dry_run=True)

    # Fast read-only gate. Ordinary Auto and all Manual tunnels stay entirely
    # on the proven V20/V21 path.
    db = SessionLocal()

    try:
        tunnel = db.get(Tunnel, tid)

        if (
            tunnel is None
            or not tunnel.is_active
            or _name(tunnel.mode or "manual") != "auto"
        ):
            delegate = True
            active = ""
            rows: list[TunnelTransport] = []
        else:
            rows = v7.enabled_rows(db, tid)
            active = _name(tunnel.active_transport)
            delegate = not active_is_explicitly_ineligible(
                rows,
                active,
            )
    finally:
        db.close()

    if delegate:
        return await base(tid, dry_run=False)

    # Ask the canonical V20 policy for its current best eligible candidate.
    # V24 is already installed, so explicitly blocked rows are absent from this
    # ranking. Dry-run preserves DB state while still using authoritative probes.
    handled, best = await base(tid, dry_run=True)

    if not should_immediate_exit(rows, active, best):
        return await base(tid, dry_run=False)

    db = SessionLocal()

    try:
        tunnel = db.get(Tunnel, tid)

        if (
            tunnel is None
            or not tunnel.is_active
            or _name(tunnel.mode or "manual") != "auto"
            or _name(tunnel.active_transport) != active
        ):
            return await base(tid, dry_run=False)

        rows_now = v7.enabled_rows(db, tid)

        if not active_is_explicitly_ineligible(
            rows_now,
            active,
        ):
            return await base(tid, dry_run=False)

        target = _active_row(rows_now, _name(best))

        if (
            target is None
            or not bool(getattr(target, "enabled", False))
            or not auto_eligible(target)
        ):
            print(
                f"[AutoEligibilityV25] HOLD tunnel={tid} "
                f"active={active} candidate={_name(best) or 'none'} "
                "reason=eligible_target_missing",
                flush=True,
            )
            return await base(tid, dry_run=False)

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))

        if iran is None or exit_node is None:
            return await base(tid, dry_run=False)

        health = await _fresh_health(
            tunnel,
            iran,
            exit_node,
            db,
            target,
        )

        if not bool(health.get("ok")):
            print(
                f"[AutoEligibilityV25] HOLD tunnel={tid} "
                f"active={active} candidate={_name(best)} "
                "reason=fresh_health_failed "
                f"error={str(health.get('error') or '')[:500]}",
                flush=True,
            )
            return await base(tid, dry_run=False)

        v7.switch_to(
            db,
            tunnel,
            _name(best),
            health,
            _name(best),
            "v25_active_explicitly_auto_ineligible",
        )

        print(
            f"[AutoEligibilityV25] EXIT tunnel={tid} "
            f"{active}->{_name(best)} fresh_health=ok",
            flush=True,
        )

        return True, _name(best)

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(
            f"[AutoEligibilityV25] ERROR tunnel={tid} "
            f"{type(exc).__name__}:{str(exc)[:900]}",
            flush=True,
        )
        return await base(tid, dry_run=False)
    finally:
        db.close()


def install_auto_ineligible_active_exit_v25() -> None:
    global _BASE_MANAGE

    if _BASE_MANAGE is None:
        _BASE_MANAGE = v7.manage_2027

    v7.manage_2027 = manage_2027_v25

    print(
        "TWINPANEL_AUTO_INELIGIBLE_ACTIVE_EXIT_V25_ACTIVE "
        "manual_unchanged=1 explicit_auto_exclusion_immediate=1 "
        "fresh_target_health_required=1",
        flush=True,
    )
