from __future__ import annotations

import asyncio

from . import tunnel_transport_manager_v10 as v10
from .legacy_ingress_reconciler import reconciler_loop as legacy_ingress_loop
from .runtime_reconciler import reconciler_loop as runtime_reconciler_loop


# ============================================================
# TWINPANEL TRANSPORT MANAGER V11
#
# V11 keeps V10/V9/V7 as the authoritative health/failover/self-heal stack
# and adds two independent ownership-safe reconcilers:
#   * orphan runtime cleanup for tunnel ids absent from DB;
#   * removal of retired per-tunnel ingress chains which can collide when
#     one Iran node fans out to several Exit nodes.
#
# Neither reconciler writes health truth, active_transport or peer reachability.
# ============================================================


async def main() -> None:
    print(
        "TWINPANEL_TRANSPORT_MANAGER_V11_START",
        flush=True,
    )

    manager_task = asyncio.create_task(
        v10.main(),
        name="twinpanel-manager-v10-core",
    )

    runtime_task = asyncio.create_task(
        runtime_reconciler_loop(),
        name="twinpanel-runtime-reconciler",
    )

    legacy_ingress_task = asyncio.create_task(
        legacy_ingress_loop(),
        name="twinpanel-legacy-ingress-reconciler",
    )

    tasks = {
        manager_task,
        runtime_task,
        legacy_ingress_task,
    }

    done, pending = await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()

    if pending:
        await asyncio.gather(
            *pending,
            return_exceptions=True,
        )

    for task in done:
        task.result()


if __name__ == "__main__":
    asyncio.run(main())
