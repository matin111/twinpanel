from __future__ import annotations

import asyncio
import json
import signal
import time
from datetime import datetime, timezone

from app.services.modern_quota_runtime_v257 import (
    MODERN_ACCOUNTING_INTERVAL_SECONDS,
    reconcile_modern_quota_once,
)


async def _run() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    while not stop.is_set():
        started = time.monotonic()
        try:
            result = await reconcile_modern_quota_once()
            print(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "event": "modern_quota_reconcile",
                        **result,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                flush=True,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "event": "modern_quota_reconcile_crash",
                        "ok": False,
                        "error": f"{type(exc).__name__}:{str(exc)[:800]}",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                flush=True,
            )

        delay = max(
            float(MODERN_ACCOUNTING_INTERVAL_SECONDS)
            - (time.monotonic() - started),
            0.25,
        )
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
