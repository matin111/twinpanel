#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import signal

from app.services.modern_quota_runtime_v257 import modern_quota_runtime_loop


async def _serve() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass

    worker = asyncio.create_task(
        modern_quota_runtime_loop(),
        name="twinpanel-modern-accounting",
    )
    stopper = asyncio.create_task(stop.wait(), name="twinpanel-accounting-stop")

    done, _pending = await asyncio.wait(
        {worker, stopper},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if worker in done:
        stopper.cancel()
        await asyncio.gather(stopper, return_exceptions=True)
        exc = worker.exception()
        if exc is not None:
            raise exc
        return

    worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(_serve())
