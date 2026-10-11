from __future__ import annotations

import asyncio

from . import tunnel_transport_manager_v8 as v8
from . import tunnel_transport_manager_v9 as v9
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport


# ============================================================
# TWINPANEL TRANSPORT MANAGER V11
#
# V11 keeps V9 authoritative validation and V8 scheduling/cooldown semantics.
# Only the relay provisioning stage changes: it uses source-aware SSH Relay V3
# so split-hop can survive Iran nodes whose actual egress IP differs from the
# Node.public_ip stored in the control plane.
# ============================================================


async def _try_all_relays_v3(
    tunnel_id: int,
) -> tuple[dict | None, dict[int, str]]:
    from .ssh_relay_v3 import provision_ssh_relay_v3

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
                f"[TransportManagerV11] RELAY_ATTEMPT "
                f"tunnel={int(tunnel_id)} relay_node={relay_id}",
                flush=True,
            )

            try:
                result = await asyncio.wait_for(
                    provision_ssh_relay_v3(
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
                        f"[TransportManagerV11] RELAY_CONFIRMED "
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
                failures[relay_id] = str(exc)[:6500]

                print(
                    f"[TransportManagerV11] RELAY_FAILED "
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
    v9._try_all_relays = _try_all_relays_v3
    v8._run_self_heal = v9._run_self_heal_authoritative

    print(
        "TWINPANEL_TRANSPORT_MANAGER_V11_START",
        flush=True,
    )

    await v8.main()


if __name__ == "__main__":
    asyncio.run(main())
