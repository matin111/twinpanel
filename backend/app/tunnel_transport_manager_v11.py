from __future__ import annotations

import asyncio

from . import tunnel_transport_manager_v10 as v10
from .legacy_ingress_reconciler import reconciler_loop as legacy_ingress_loop
from .runtime_reconciler_v2 import reconciler_loop as runtime_reconciler_loop
from .manager_runtime_v20 import install_manager_runtime_v20


# ============================================================
# TWINPANEL TRANSPORT MANAGER V11 + PERFORMANCE AUTO V20
#
# V11 keeps V10/V9/V7 as the authoritative health/failover/self-heal stack
# and adds two independent ownership-safe reconcilers:
#   * orphan runtime cleanup for tunnel ids absent from DB;
#   * removal of retired per-tunnel ingress chains which can collide when
#     one Iran node fans out to several Exit nodes.
#
# Manager Runtime V20 keeps all V19/V16 self-hosted and multi-exit Backhaul
# hooks, preserves Manual authority, and upgrades Auto selection so every
# supported healthy transport can compete on measured path quality.
#
# Runtime reconciliation uses V2's serialization-safe cleanup wrapper while
# preserving V1's DB ownership and confirmation guards.
# Neither reconciler writes health truth, active_transport or peer reachability.
# ============================================================


async def main() -> None:
    install_manager_runtime_v20()

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
