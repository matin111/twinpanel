from __future__ import annotations

import asyncio
from typing import Any


MARKER = "TWINPANEL_CONVERGENCE_EVENT_LOOP_ISOLATION_V1"
_installed = False


def _run_reconcile(runtime: Any) -> dict:
    """Run the existing convergence coroutine in a worker-thread event loop."""

    return asyncio.run(runtime.reconcile_installed_exit_nodes_once())


def install() -> None:
    """Keep historical subscription convergence off Uvicorn's event loop.

    This patch changes scheduling only. The canonical V114/V299 convergence
    implementation, topology signature, retry cadence, provisioning functions,
    credential rules and quota behavior remain authoritative and unchanged.
    """

    global _installed
    if _installed:
        return

    from . import node_subscription_convergence_v114 as runtime

    async def _isolated_convergence_loop() -> None:
        await asyncio.sleep(runtime._INITIAL_DELAY_SECONDS)

        while True:
            stage = "topology_signature"
            try:
                signature = await asyncio.to_thread(runtime._topology_signature)
                if signature != runtime._last_topology_signature:
                    stage = "reconcile"
                    result = await asyncio.to_thread(_run_reconcile, runtime)
                    changed = [
                        item
                        for item in result.get("nodes", [])
                        if (
                            item.get("membership_added")
                            or item.get("provisioned_pairs")
                            or item.get("skipped_missing_plan")
                            or item.get("failed_count")
                        )
                    ]
                    if changed:
                        print(runtime.DYNAMIC_MARKER, changed, flush=True)
                    if result.get("ok"):
                        stage = "post_reconcile_signature"
                        runtime._last_topology_signature = await asyncio.to_thread(
                            runtime._topology_signature
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    f"{runtime.DYNAMIC_MARKER}_FAILED",
                    f"stage={stage}",
                    type(exc).__name__,
                    flush=True,
                )

            await asyncio.sleep(runtime._RETRY_INTERVAL_SECONDS)

    runtime._convergence_loop = _isolated_convergence_loop
    _installed = True
    print(
        f"{MARKER}_ACTIVE scheduling=worker_thread "
        "convergence=v114-v299 semantics=unchanged",
        flush=True,
    )
