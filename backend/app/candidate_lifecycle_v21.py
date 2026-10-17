from __future__ import annotations

from .lifecycle_cleanup import cleanup_tunnel_runtime as _base_cleanup_tunnel_runtime
from .models import TunnelTransport
from .transport_candidates import SPECS, uninstall_transport


# ============================================================
# TWINPANEL MODERN CANDIDATE LIFECYCLE V21
#
# A logical tunnel may now own several isolated L3 canaries. Deleting the
# logical tunnel must remove those candidate services/interfaces/firewall rules
# before the DB identity disappears; otherwise the orphan reconciler would be
# forced to clean them much later.
# ============================================================


async def cleanup_tunnel_runtime_v21(
    tunnel,
    db,
) -> dict:
    tid = int(tunnel.id)

    rows = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tid,
            TunnelTransport.transport.in_(tuple(SPECS)),
        )
        .all()
    )

    installed = {
        str(row.transport or "").strip().lower()
        for row in rows
        if str(row.transport or "").strip().lower() in SPECS
    }

    candidate_results = []
    candidate_errors = []

    # Candidate cleanup is narrow and ownership-tagged inside each installer:
    # only its own systemd units, interface, policy table and exact firewall/NAT
    # rules are removed. Existing VPN services and fallback transports remain.
    for name in sorted(installed):
        try:
            result = await uninstall_transport(
                name,
                tid,
                db,
            )
            candidate_results.append(result)
        except Exception as exc:
            db.rollback()
            candidate_errors.append(
                f"{name}:{type(exc).__name__}:{str(exc)[:1200]}"
            )

    base_result = None
    base_error = None

    try:
        base_result = await _base_cleanup_tunnel_runtime(
            tunnel,
            db,
        )
    except Exception as exc:
        base_error = (
            f"base:{type(exc).__name__}:{str(exc)[:1800]}"
        )

    errors = list(candidate_errors)
    if base_error:
        errors.append(base_error)

    if errors:
        raise RuntimeError(
            " | ".join(errors)[:4000]
        )

    return {
        "ok": True,
        "tunnel_id": tid,
        "candidate_results": candidate_results,
        "base": base_result,
    }
