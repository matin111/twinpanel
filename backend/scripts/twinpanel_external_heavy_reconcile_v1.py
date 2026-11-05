#!/usr/bin/env python3
"""Run canonical quota/convergence scheduling outside the interactive API."""
from __future__ import annotations
import asyncio
import fcntl
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.pop("TWINPANEL_EXTERNAL_HEAVY_RECONCILE", None)

async def main() -> None:
    from app import node_subscription_convergence_v114 as convergence
    from app.services import customer_maintenance as maintenance
    with open("/run/twinpanel-external-heavy-reconcile.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        tasks = [asyncio.create_task(convergence._convergence_loop(), name="convergence"),
                 asyncio.create_task(maintenance._quota_runtime_worker(), name="quota")]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if not t.cancelled():
                    exc=t.exception()
                    if exc:raise exc
            raise RuntimeError("heavy reconciliation worker unexpectedly exited")
        finally:
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
