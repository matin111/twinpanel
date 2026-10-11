from __future__ import annotations

import asyncio

from . import tunnel_transport_manager_v10 as v10
from .runtime_reconciler import reconciler_loop


# ============================================================
# TWINPANEL TRANSPORT MANAGER V11
#
# V11 keeps V10/V9/V7 as the authoritative health/failover/self-heal stack
# and adds an independent ownership-safe runtime reconciler.
#
# The reconciler only removes TwinPanel runtime ids which are absent from the
# entire tunnels table and which have been observed as orphaned repeatedly.
# It never changes health truth, active_transport, peer reachability or any
# runtime belonging to an existing logical tunnel.
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

    reconciler_task = asyncio.create_task(
        reconciler_loop(),
        name="twinpanel-runtime-reconciler",
    )

    tasks = {
        manager_task,
        reconciler_task,
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
