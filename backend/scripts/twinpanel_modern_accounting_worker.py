#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

# This file is executed directly by systemd from backend/scripts. Python sets
# sys.path[0] to that scripts directory, not to the backend package root, so the
# sibling `app` package is otherwise not importable. Bootstrap the backend root
# before importing application modules; this keeps the worker independent of the
# caller's current directory and avoids relying on a global PYTHONPATH.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Keep the legacy import visible for rollback/source validation, but production
# execution uses the deadlock-safe V314 orchestration. V314 reuses the proven
# V257 protocol collectors while separating async network I/O from DB writes.
# The independent subprocess takes exclusive responsibility for Mieru
# presence. This flag also disables Mieru in heavy V314 sweeps. Setting it
# explicitly to 0 is a safe rollback to the original V314 behavior.
os.environ.setdefault("TP_MIERU_INDEPENDENT_WORKER", "1")

from app.services.modern_quota_runtime_v257 import modern_quota_runtime_loop as legacy_modern_quota_runtime_loop
from app.services.modern_quota_runtime_v314 import modern_quota_runtime_loop
from app.services.singbox_native_accounting_v265 import singbox_native_accounting_loop
from app.services import modern_quota_runtime_v314 as modern_quota_runtime_v314_module
from app.services import singbox_native_accounting_v265 as singbox_native_accounting_v265_module
from app.services.accounting_device_map_batch_v1 import (
    install_accounting_device_batch_cache,
)


# Full modern/Sing-box accounting reconciliation performs network collection,
# DB matching and quota writes. A 5-second full sweep kept production CPUs busy
# continuously on controllers with hundreds of subscriptions. Preserve all
# accounting semantics while reducing redundant sweeps to a 15-second cadence.
# This only affects telemetry freshness; provisioning, credentials, sessions,
# quota limits and protocol dataplane behavior are unchanged.
ACCOUNTING_RECONCILE_INTERVAL_SECONDS = 45.0
modern_quota_runtime_v314_module.MODERN_ACCOUNTING_INTERVAL_SECONDS = (
    ACCOUNTING_RECONCILE_INTERVAL_SECONDS
)
singbox_native_accounting_v265_module.SINGBOX_ACCOUNTING_INTERVAL_SECONDS = (
    ACCOUNTING_RECONCILE_INTERVAL_SECONDS
)

# The accounting collectors historically import the node-oriented device
# builder directly. Install a worker-local replacement before either loop starts
# so one fresh SQLAlchemy Session builds the full credential/device mapping once
# and every node in that same reconcile pass reuses it. No global API/runtime
# caller is changed and each next sweep receives a fresh Session/cache.
install_accounting_device_batch_cache()


async def _mieru_fast_subprocess(proc: asyncio.subprocess.Process) -> None:
    """Supervise the already-started fast worker without waiting on V314."""
    try:
        status = await proc.wait()
        raise RuntimeError(f"mieru_fast_presence_worker_exited:{status}")
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=7)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()


async def _serve() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass

    # IMPORTANT: start this OS process *before* scheduling the heavyweight
    # V314 and sing-box tasks. Their synchronous SQLAlchemy work can monopolize
    # the asyncio loop for minutes; if subprocess creation is merely scheduled
    # as another coroutine, the fast worker never even starts.
    fast_proc = None
    if os.environ.get("TP_MIERU_INDEPENDENT_WORKER") == "1":
        fast_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(BACKEND_ROOT / "scripts/twinpanel_mieru_fast_presence_worker.py"),
        )

    workers = (
        asyncio.create_task(
            modern_quota_runtime_loop(),
            name="twinpanel-modern-accounting",
        ),
        asyncio.create_task(
            singbox_native_accounting_loop(),
            name="twinpanel-singbox-native-accounting-v265",
        ),
        *(
            (
                asyncio.create_task(
                    _mieru_fast_subprocess(fast_proc),
                    name="twinpanel-mieru-fast-presence",
                ),
            )
            if os.environ.get("TP_MIERU_INDEPENDENT_WORKER") == "1"
            else ()
        ),
    )
    stopper = asyncio.create_task(stop.wait(), name="twinpanel-accounting-stop")

    done, _pending = await asyncio.wait(
        {*workers, stopper},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if stopper in done:
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        return

    # A collector must be long-lived. If either collector exits unexpectedly,
    # stop the sibling and fail this process so systemd can restart the complete
    # accounting worker rather than leaving a partially healthy accounting path.
    stopper.cancel()
    for worker in workers:
        if worker not in done:
            worker.cancel()
    await asyncio.gather(stopper, *workers, return_exceptions=True)

    for worker in workers:
        if worker not in done:
            continue
        exc = worker.exception()
        if exc is not None:
            raise exc
        raise RuntimeError(
            f"accounting collector exited unexpectedly: {worker.get_name()}"
        )


if __name__ == "__main__":
    asyncio.run(_serve())
