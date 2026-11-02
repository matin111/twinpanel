from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any


# TWINPANEL_MANUAL_CUTOVER_PEER_KEY_GRACE_V1
#
# A brand-new WireGuard-backed tunnel has a normal two-report convergence:
# each Agent first creates/reports its local public key, then the controller can
# publish that key to the opposite peer in desired state. The first fresh Agent
# report can therefore legitimately contain `waiting_peer_key`.
#
# V257 previously treated every fresh negative report as authoritative failure
# and rolled the new tunnel back immediately. Preserve fail-fast for real
# dataplane errors, but allow only `waiting_peer_key` to keep polling inside the
# existing 30-second acceptance window.

_INSTALLED = False


async def _wait_manual_cutover_acceptance_peer_key_grace(
    db: Any,
    tunnel: Any,
    *,
    name: str,
    started_at: datetime,
    timeout_seconds: float = 30.0,
):
    from .routers import modern_transports as mt

    node_ids = (
        int(tunnel.iran_node_id),
        int(tunnel.exit_node_id),
    )
    deadline = asyncio.get_running_loop().time() + float(timeout_seconds)
    last_snapshot: list[dict] = []

    while True:
        db.expire_all()
        rows = {
            int(item.node_id): item
            for item in (
                db.query(mt.TunnelPeerState)
                .filter(
                    mt.TunnelPeerState.tunnel_id == int(tunnel.id),
                    mt.TunnelPeerState.node_id.in_(node_ids),
                )
                .all()
            )
        }

        last_snapshot = [
            mt._peer_cutover_snapshot_v257(
                rows.get(node_id),
                node_id=node_id,
                started_at=started_at,
                name=name,
            )
            for node_id in node_ids
        ]

        if all(item["accepted"] for item in last_snapshot):
            return True, last_snapshot, None

        for item in last_snapshot:
            if (
                item["fresh"]
                and item["selected_transport"] == name
                and not item["accepted"]
            ):
                reason = str(
                    item.get("last_error")
                    or "manual_cutover_peer_not_reachable"
                ).strip()

                if reason == "waiting_peer_key":
                    # Expected first-pass convergence for a brand-new peer.
                    # Keep the existing deadline authoritative and wait for the
                    # next desired-state/report cycle to carry the peer key.
                    continue

                return False, last_snapshot, reason[:900]

        if asyncio.get_running_loop().time() >= deadline:
            return (
                False,
                last_snapshot,
                "manual_cutover_agent_confirmation_timeout",
            )

        await asyncio.sleep(1.0)


def install() -> None:
    global _INSTALLED

    if _INSTALLED:
        return

    from .routers import modern_transports as mt

    current = mt._wait_manual_cutover_acceptance_v257
    if getattr(current, "_twinpanel_manual_cutover_peer_key_grace_v1", False):
        _INSTALLED = True
        return

    _wait_manual_cutover_acceptance_peer_key_grace._twinpanel_manual_cutover_peer_key_grace_v1 = True
    mt._wait_manual_cutover_acceptance_v257 = (
        _wait_manual_cutover_acceptance_peer_key_grace
    )
    _INSTALLED = True

    print(
        "TWINPANEL_MANUAL_CUTOVER_PEER_KEY_GRACE_V1_ACTIVE "
        "transient=waiting_peer_key timeout=unchanged failfast=other-errors",
        flush=True,
    )
