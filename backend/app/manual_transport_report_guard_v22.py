from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session as SASession

from .models import Tunnel, TunnelPeerState


# ============================================================
# TWINPANEL MANUAL TRANSPORT REPORT AUTHORITY V22
#
# Root cause fixed here:
#   A node Agent can legitimately report its previous selected_transport for
#   one polling/report cycle immediately after an administrator switches a
#   tunnel from Auto to Manual. routers/tunnels.py treats non-Auto reports as
#   allowed to copy that telemetry back into tunnel.active_transport. That
#   creates a short race where the stale report can undo the administrator's
#   Manual selection before the Agent has fetched the new desired state.
#
# Manual authority is represented by preferred_transport. During a peer-report
# flush, if the same tunnel is Manual, keep aggregate active_transport pinned to
# preferred_transport. Peer and TunnelTransport telemetry are still committed.
# Auto mode is untouched: Transport Manager remains its sole aggregate writer.
#
# The guard is intentionally scoped to transactions which modify/create a
# TunnelPeerState, so normal admin/API edits are not rewritten by this hook.
# ============================================================


def _name(value) -> str:
    return str(value or "").strip().lower()


def enforce_manual_report_authority(session: SASession) -> int:
    peer_tunnel_ids: set[int] = set()

    for obj in tuple(session.new) + tuple(session.dirty):
        if not isinstance(obj, TunnelPeerState):
            continue

        try:
            tunnel_id = int(obj.tunnel_id)
        except (TypeError, ValueError):
            continue

        if tunnel_id > 0:
            peer_tunnel_ids.add(tunnel_id)

    if not peer_tunnel_ids:
        return 0

    corrected = 0

    for obj in tuple(session.dirty):
        if not isinstance(obj, Tunnel):
            continue

        try:
            tunnel_id = int(obj.id)
        except (TypeError, ValueError):
            continue

        if tunnel_id not in peer_tunnel_ids:
            continue

        if _name(obj.mode) != "manual":
            continue

        preferred = _name(obj.preferred_transport)
        if not preferred:
            continue

        if _name(obj.active_transport) == preferred:
            continue

        obj.active_transport = preferred
        corrected += 1

    return corrected


def _before_flush(session, flush_context, instances) -> None:
    corrected = enforce_manual_report_authority(session)

    if corrected:
        print(
            "TWINPANEL_MANUAL_REPORT_AUTHORITY_V22 "
            f"corrected={corrected}",
            flush=True,
        )


_INSTALLED = False


def apply_manual_transport_report_guard_v22() -> None:
    global _INSTALLED

    if _INSTALLED:
        return

    if not event.contains(
        SASession,
        "before_flush",
        _before_flush,
    ):
        event.listen(
            SASession,
            "before_flush",
            _before_flush,
        )

    _INSTALLED = True
