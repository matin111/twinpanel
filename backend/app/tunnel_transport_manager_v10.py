from __future__ import annotations

import asyncio

from . import tunnel_transport_manager_v8 as v8
from . import tunnel_transport_manager_v9 as v9
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport


# ============================================================
# TWINPANEL TRANSPORT MANAGER V10 + RELAY V22
#
# V10 keeps V9 authoritative physical/full-egress validation,
# but every autonomous Relay attempt now uses V22.
#
# This prevents an old V2 retry from tearing down a healthy
# Carrier-aware V21/V22 Relay.
# ============================================================


RELAY_ATTEMPT_TIMEOUT_V22 = 270


async def _try_all_relays_v22(
    tunnel_id: int,
) -> tuple[
    dict | None,
    dict[int, str],
]:
    from .ssh_relay_v22 import (
        provision_ssh_relay_v22,
    )

    db = SessionLocal()

    failures: dict[int, str] = {}

    try:
        tunnel = db.get(
            Tunnel,
            int(tunnel_id),
        )

        if tunnel is None:
            raise RuntimeError(
                "tunnel_not_found"
            )

        iran = db.get(
            Node,
            int(tunnel.iran_node_id),
        )

        exit_node = db.get(
            Node,
            int(tunnel.exit_node_id),
        )

        if (
            iran is None
            or exit_node is None
        ):
            raise RuntimeError(
                "relay_endpoint_node_missing"
            )

        candidates = (
            v9._eligible_relay_nodes(
                db,
                tunnel,
            )
        )

        if not candidates:
            failures[0] = (
                "no eligible online relay node "
                "with saved root access"
            )

        for relay in candidates:
            relay_id = int(
                relay.id
            )

            print(
                "[TransportManagerV10] "
                "RELAY_V22_ATTEMPT "
                f"tunnel={int(tunnel_id)} "
                f"relay_node={relay_id}",
                flush=True,
            )

            try:
                result = (
                    await
                    asyncio.wait_for(
                        provision_ssh_relay_v22(
                            tunnel,
                            iran,
                            relay,
                            exit_node,
                            db,
                        ),
                        timeout=(
                            RELAY_ATTEMPT_TIMEOUT_V22
                        ),
                    )
                )

                db.expire_all()

                row = v9._relay_row(
                    db,
                    int(tunnel_id),
                )

                if row is not None:
                    row.priority = (
                        v9.RELAY_PRIORITY
                    )
                    db.commit()

                state = (
                    await
                    v9._authoritative_refresh(
                        int(tunnel_id)
                    )
                )

                if bool(
                    state.get(
                        "operational"
                    )
                ):
                    print(
                        "[TransportManagerV10] "
                        "RELAY_V22_CONFIRMED "
                        f"tunnel={int(tunnel_id)} "
                        f"relay_node={relay_id} "
                        "active="
                        f"{state.get('active_transport')}",
                        flush=True,
                    )

                    return (
                        result,
                        failures,
                    )

                failures[
                    relay_id
                ] = (
                    "relay V22 provisioned but "
                    "authoritative V7 full-egress "
                    "probe did not confirm an "
                    "operational dataplane"
                )

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                db.rollback()

                failures[
                    relay_id
                ] = str(
                    exc
                )[:4000]

                print(
                    "[TransportManagerV10] "
                    "RELAY_V22_FAILED "
                    f"tunnel={int(tunnel_id)} "
                    f"relay_node={relay_id} "
                    "error="
                    f"{failures[relay_id]!r}",
                    flush=True,
                )

        db.expire_all()

        row = v9._relay_row(
            db,
            int(tunnel_id),
        )

        if row is None:
            row = TunnelTransport(
                tunnel_id=int(
                    tunnel_id
                ),
                transport=(
                    "ssh_relay"
                ),
                priority=(
                    v9.RELAY_PRIORITY
                ),
                enabled=False,
                status="offline",
            )

            db.add(
                row
            )

        row.priority = (
            v9.RELAY_PRIORITY
        )

        row.enabled = False
        row.status = "offline"
        row.latency_ms = None

        row.last_error = (
            "all_relay_candidates_failed: "
            + "; ".join(
                (
                    f"node={node_id}:"
                    f"{message}"
                )
                for (
                    node_id,
                    message,
                )
                in failures.items()
            )
        )[:6500]

        db.commit()

        return (
            None,
            failures,
        )

    finally:
        db.close()


async def main() -> None:
    # V9 worker resolves this symbol from module globals.
    v9._try_all_relays = (
        _try_all_relays_v22
    )

    v8._run_self_heal = (
        v9._run_self_heal_authoritative
    )

    print(
        "TWINPANEL_TRANSPORT_MANAGER_V10_START",
        flush=True,
    )

    print(
        "TWINPANEL_TRANSPORT_MANAGER_RELAY_V22_ACTIVE "
        "authoritative_full_egress=1 "
        "legacy_v2_retry=0",
        flush=True,
    )

    await v8.main()


if __name__ == "__main__":
    asyncio.run(
        main()
    )
