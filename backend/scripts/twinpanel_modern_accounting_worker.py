#!/usr/bin/env python3
from __future__ import annotations

import asyncio
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

from app.services.modern_quota_runtime_v257 import modern_quota_runtime_loop
from app.services.singbox_native_accounting_v265 import singbox_native_accounting_loop


async def _serve() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass

    workers = (
        asyncio.create_task(
            modern_quota_runtime_loop(),
            name="twinpanel-modern-accounting",
        ),
        asyncio.create_task(
            singbox_native_accounting_loop(),
            name="twinpanel-singbox-native-accounting-v265",
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
