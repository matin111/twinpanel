from __future__ import annotations

import asyncio

from . import tunnel_transport_manager_v8 as v8
from . import tunnel_transport_manager_v9 as v9
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport


# ============================================================
# TWINPANEL TRANSPORT MANAGER V10
#
# V10 keeps V9 authoritative physical validation and replaces only the SSH
# Relay attempt with the hardened relay V2 preflight. The scheduler, grace,
# concurrency and cooldown policies remain V8/V9 behavior.
# ============================================================


async def _try_all_relays_v2(
    tunnel_id: int,
) -> tuple[dict | None, dict[int, str]]:
    from .ssh_relay_v2 import provision_ssh_relay_v2

    db = SessionLocal()
    failures: dict[int, str] = {}

    try:
        tunnel = db.get(Tunnel, int(tunnel_id))
        if tunnel is None:
            raise RuntimeError("tunnel_not_found")

        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if iran is None or exit_node is None:
            raise RuntimeError("relay_endpoint_node_missing")

        candidates = v9._eligible_relay_nodes(db, tunnel)

        if not candidates:
            failures[0] = "no eligible online relay node with saved root access"

        for relay in candidates:
            relay_id = int(relay.id)

            print(
                f"[TransportManagerV10] RELAY_ATTEMPT "
                f"tunnel={int(tunnel_id)} relay_node={relay_id}",
                flush=True,
            )

            try:
                result = await asyncio.wait_for(
                    provision_ssh_relay_v2(
                        tunnel,
                        iran,
                        relay,
                        exit_node,
                        db,
                    ),
                    timeout=v9.RELAY_ATTEMPT_TIMEOUT,
                )

                db.expire_all()
                row = v9._relay_row(db, int(tunnel_id))
                if row is not None:
                    row.priority = v9.RELAY_PRIORITY
                    db.commit()

                state = await v9._authoritative_refresh(
                    int(tunnel_id)
                )

                if bool(state.get("operational")):
                    print(
                        f"[TransportManagerV10] RELAY_CONFIRMED "
                        f"tunnel={int(tunnel_id)} relay_node={relay_id} "
                        f"active={state.get('active_transport')}",
                        flush=True,
                    )
                    return result, failures

                failures[relay_id] = (
                    "relay provisioned but authoritative V7 probe did not "
                    "confirm an operational dataplane"
                )

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                db.rollback()
                failures[relay_id] = str(exc)[:4000]

                print(
                    f"[TransportManagerV10] RELAY_FAILED "
                    f"tunnel={int(tunnel_id)} relay_node={relay_id} "
                    f"error={failures[relay_id]!r}",
                    flush=True,
                )

        db.expire_all()
        row = v9._relay_row(db, int(tunnel_id))
        if row is None:
            row = TunnelTransport(
                tunnel_id=int(tunnel_id),
                transport="ssh_relay",
                priority=v9.RELAY_PRIORITY,
                enabled=False,
                status="offline",
            )
            db.add(row)

        row.priority = v9.RELAY_PRIORITY
        row.enabled = False
        row.status = "offline"
        row.latency_ms = None
        row.last_error = (
            "all_relay_candidates_failed: "
            + "; ".join(
                f"node={node_id}:{message}"
                for node_id, message in failures.items()
            )
        )[:6500]
        db.commit()

        return None, failures

    finally:
        db.close()


async def main() -> None:
    # V9's worker resolves _try_all_relays from V9 module globals at runtime.
    # Replace only that relay stage, then keep V9 as the authoritative worker.
    v9._try_all_relays = _try_all_relays_v2
    v8._run_self_heal = v9._run_self_heal_authoritative

    print(
        "TWINPANEL_TRANSPORT_MANAGER_V10_START",
        flush=True,
    )

    await v8.main()


if __name__ == "__main__":
    asyncio.run(main())
